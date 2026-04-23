from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog

from app.config import Settings
from app.db import Database
from app.models import ItemStatus, RawItem
from app.services.dedup import DedupService
from app.services.extractor import Extractor
from app.services.publisher import Publisher
from app.services.relevance import RelevanceEngine
from app.services.rewrite import RewriteService
from app.sources.base import SourceConfig
from app.sources.optional_generic import build_generic_source
from app.sources.social_stubs import InstagramSource
from app.sources import (
    clutch,
    concert_ua,
    glavred,
    ictv_fakty,
    insider_ua,
    karabas,
    kontramarka,
    luxfm,
    novyny_live,
    novyny_live_stars,
    nv_life,
    oboz,
    odna_hvylyna,
    one_plus_one,
    rbc_lite,
    tabloid_pravda,
    ticketsbox,
    tsn,
    unian,
    viva,
    ukrnet_showbiz,
    zirki,
)

log = structlog.get_logger()


@dataclass(slots=True)
class SourceDiagnostics:
    fetched: int = 0
    relevant: int = 0
    irrelevant: int = 0
    too_old: int = 0
    duplicate: int = 0
    queued: int = 0
    retry: int = 0
    published: int = 0
    fetch_error: str = ""

    def as_dict(self) -> dict[str, int | str]:
        data: dict[str, int | str] = {
            "fetched": self.fetched,
            "relevant": self.relevant,
            "irrelevant": self.irrelevant,
            "too_old": self.too_old,
            "duplicate": self.duplicate,
            "queued": self.queued,
            "retry": self.retry,
            "published": self.published,
        }
        if self.fetch_error:
            data["fetch_error"] = self.fetch_error
        return data


@dataclass(slots=True)
class RunStats:
    scanned_sources: int = 0
    discovered_count: int = 0
    relevant_count: int = 0
    published_count: int = 0
    error_count: int = 0
    notes: list[str] | None = None
    source_breakdown: dict[str, SourceDiagnostics] | None = None

    def note(self, value: str) -> None:
        if self.notes is None:
            self.notes = []
        self.notes.append(value)

    def source(self, name: str) -> SourceDiagnostics:
        if self.source_breakdown is None:
            self.source_breakdown = {}
        if name not in self.source_breakdown:
            self.source_breakdown[name] = SourceDiagnostics()
        return self.source_breakdown[name]

    def source_breakdown_dict(self) -> dict[str, dict[str, int | str]]:
        return {
            name: data.as_dict()
            for name, data in sorted((self.source_breakdown or {}).items())
        }


class SourceRunner:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self.extractor = Extractor()
        self.dedup = DedupService(db, fuzzy_threshold=settings.fuzzy_dup_threshold)
        self.rewriter = RewriteService(
            language=settings.app_language,
            enable_openai=settings.enable_openai,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            content_scope=settings.content_scope,
        )
        self.publisher = Publisher(settings, db)
        self._last_published_at: datetime | None = None

    def _effective_publish_delay_seconds(self) -> int:
        delay = self.settings.delayed_publish_seconds
        if self.settings.content_scope == "stars":
            return max(delay, 90)
        return delay

    async def run_once(self, *, publish_queue: bool = True) -> RunStats:
        run_id = self.db.create_run()
        stats = RunStats()
        try:
            requeued_failed = self.db.requeue_failed_items()
            if requeued_failed:
                stats.note(f"requeued_failed:{requeued_failed}")
            tracked = self.db.get_tracked_entities()
            relevance = RelevanceEngine(
                tracked,
                threshold=self.settings.relevance_threshold,
                content_scope=self.settings.content_scope,
            )
            sources = self._build_sources()
            stats.scanned_sources = len(sources)
            if publish_queue:
                await self._publish_ready_queue(stats)
            for source in sources:
                source_stats = stats.source(source.config.name)
                raw_items = source.safe_fetch()
                if getattr(source, "last_fetch_error", ""):
                    source_stats.fetch_error = source.last_fetch_error
                source_stats.fetched += len(raw_items)
                stats.discovered_count += len(raw_items)
                log.info(
                    "source_scan_completed",
                    source=source.config.name,
                    fetched=len(raw_items),
                    fetch_error=source_stats.fetch_error or None,
                )
                for raw in raw_items:
                    await self._handle_item(raw, relevance, stats)
            if publish_queue:
                await self._publish_ready_queue(stats)
        except Exception as exc:
            stats.error_count += 1
            stats.note(str(exc))
            log.exception("run_failed", error=str(exc))
        finally:
            self._write_source_monitoring(stats)
            log.info("source_breakdown", sources=stats.source_breakdown_dict())
            self.db.finish_run(
                run_id=run_id,
                scanned_sources=stats.scanned_sources,
                discovered_count=stats.discovered_count,
                relevant_count=stats.relevant_count,
                published_count=stats.published_count,
                error_count=stats.error_count,
                notes="; ".join(stats.notes or []),
            )
        return stats

    async def publish_ready_once(self) -> int:
        stats = RunStats()
        await self._publish_ready_queue(stats)
        return stats.published_count

    async def _handle_item(self, raw: RawItem, relevance: RelevanceEngine, stats: RunStats) -> None:
        source_id = self.db.source_id_by_name(raw.source_name)
        source_meta = self.db.source_metadata_by_name(raw.source_name) or {}
        raw.metadata.update(
            {
                "source_priority": source_meta.get("priority", 50),
                "source_credibility": source_meta.get("credibility_score", 70),
                "source_entertainment_bias": source_meta.get("entertainment_bias_score", 70),
            }
        )
        result = relevance.analyze(raw)
        source_stats = stats.source(raw.source_name)
        if not result.is_relevant:
            normalized = self.extractor.normalize(raw, source_id, result)
            self.db.insert_discovered_item(normalized, status=ItemStatus.IRRELEVANT)
            source_stats.irrelevant += 1
            return

        stats.relevant_count += 1
        source_stats.relevant += 1
        normalized = self.extractor.normalize(raw, source_id, result)
        if self._is_too_old_for_publishing(normalized):
            self.db.insert_discovered_item(normalized, status=ItemStatus.IRRELEVANT)
            source_stats.too_old += 1
            stats.note(f"too_old:{raw.source_name}:{raw.url}")
            return
        duplicate = self.dedup.check_duplicate(normalized)
        if duplicate.reason and duplicate.reason.startswith("retry:") and duplicate.duplicate_group_id:
            self.db.mark_item_status(duplicate.duplicate_group_id, ItemStatus.READY)
            source_stats.retry += 1
            source_stats.queued += 1
            stats.note(f"queued_retry:{raw.source_name}:{raw.url}")
            return
        if duplicate.is_duplicate:
            normalized.duplicate_group_id = duplicate.duplicate_group_id
            normalized.is_primary_story = False
            item_id = self.db.insert_discovered_item(normalized, status=ItemStatus.DUPLICATE)
            source_stats.duplicate += 1
            stats.note(f"duplicate:{duplicate.reason}:{raw.source_name}:{raw.url}")
            if item_id is None:
                return
            return

        item_id = self.db.insert_discovered_item(normalized, status=ItemStatus.READY)
        if item_id is None:
            item_id = self.db.reactivate_irrelevant_item(normalized, status=ItemStatus.READY)
            if item_id is None:
                return
            stats.note(f"reactivated_previously_irrelevant:{raw.source_name}:{raw.url}")
        source_stats.queued += 1
        stats.note(f"queued_for_publish:{raw.source_name}:{raw.url}")

    async def _publish_ready_queue(self, stats: RunStats) -> None:
        # Preview mode does not change item statuses, so we avoid an infinite loop.
        single_pass = self.settings.preview_mode or not (
            self.settings.auto_publish or self.settings.telegram_admin_chat_id
        )
        while True:
            wave_size = max(self.settings.max_publish_per_run or 50, 1)
            candidates = self.db.ready_items_for_publish(limit=max(wave_size * 20, 100))
            if not candidates:
                break
            for item_id, item in self._fair_ready_items(candidates, min(len(candidates), wave_size)):
                stats.note(f"publishing_queued:{item.source_name}:{item.url}")
                await self._rewrite_and_publish(item_id, item, stats)
            if single_pass:
                break

    def _fair_ready_items(self, candidates, limit: int):
        by_source: dict[str, list] = {}
        source_order: list[str] = []
        for item_id, item in candidates:
            if item.source_name not in by_source:
                by_source[item.source_name] = []
                source_order.append(item.source_name)
            by_source[item.source_name].append((item_id, item))

        selected = []
        while len(selected) < limit and any(by_source.values()):
            for source_name in source_order:
                items = by_source[source_name]
                if not items:
                    continue
                selected.append(items.pop(0))
                if len(selected) >= limit:
                    break
        return selected

    def _write_source_monitoring(self, stats: RunStats) -> None:
        if not stats.source_breakdown:
            return

        now = datetime.now(UTC).isoformat()
        db_stem = self.settings.db_path.stem or "app"
        monitor_dir = self.settings.db_path.parent / "monitoring"
        monitor_dir.mkdir(parents=True, exist_ok=True)

        latest_path = monitor_dir / f"{db_stem}_source_health_latest.json"
        history_path = monitor_dir / f"{db_stem}_source_health_history.jsonl"

        platforms = []
        for name, data in sorted(stats.source_breakdown.items()):
            total_rejections = data.irrelevant + data.too_old + data.duplicate
            rejected_reasons: dict[str, int] = {}
            if data.irrelevant:
                rejected_reasons["irrelevant"] = data.irrelevant
            if data.too_old:
                rejected_reasons["too_old"] = data.too_old
            if data.duplicate:
                rejected_reasons["duplicate"] = data.duplicate
            if data.fetch_error:
                rejected_reasons["fetch_error"] = 1

            status = "ok"
            if data.fetch_error:
                status = "failed_fetch"
            elif data.fetched == 0:
                status = "no_items"

            primary_failure_reason = ""
            if data.fetch_error:
                primary_failure_reason = data.fetch_error
            elif total_rejections > 0 and data.relevant == 0:
                if data.too_old:
                    primary_failure_reason = "all_items_too_old"
                elif data.duplicate:
                    primary_failure_reason = "all_items_duplicate"
                elif data.irrelevant:
                    primary_failure_reason = "all_items_irrelevant"

            platforms.append(
                {
                    "source": name,
                    "status": status,
                    "primary_failure_reason": primary_failure_reason,
                    "fetched": data.fetched,
                    "relevant": data.relevant,
                    "published": data.published,
                    "queued": data.queued,
                    "retry": data.retry,
                    "rejected_reasons": rejected_reasons,
                }
            )

        payload = {
            "generated_at": now,
            "profile": self.settings.app_profile,
            "content_scope": self.settings.content_scope,
            "db_path": str(self.settings.db_path),
            "totals": {
                "sources": len(platforms),
                "fetched": sum(item["fetched"] for item in platforms),
                "relevant": sum(item["relevant"] for item in platforms),
                "published": sum(item["published"] for item in platforms),
                "queued": sum(item["queued"] for item in platforms),
            },
            "platforms": platforms,
        }

        latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        with history_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    async def _rewrite_and_publish(self, item_id: int, normalized, stats: RunStats) -> None:
        rewrite = self.rewriter.rewrite(normalized)

        if self.settings.preview_mode or not (self.settings.auto_publish or self.settings.telegram_admin_chat_id):
            log.info("preview_post", title=normalized.title, text=rewrite.text)
            return

        delay_seconds = self._effective_publish_delay_seconds()
        if delay_seconds and self._last_published_at is not None:
            elapsed_seconds = (datetime.now(UTC) - self._last_published_at).total_seconds()
            if elapsed_seconds < delay_seconds:
                await asyncio.sleep(delay_seconds - elapsed_seconds)
        publish_result = await self.publisher.publish(item_id, normalized, rewrite)
        if publish_result.sent or publish_result.dry_run:
            stats.published_count += 1
            stats.source(normalized.source_name).published += 1
            self._last_published_at = datetime.now(UTC)

    def _build_sources(self):
        configured = {row["name"]: row for row in self.db.get_enabled_sources()}
        named_factories = {
            "TSN Glamur": tsn.make_source,
            "UNIAN Lite Stars": unian.make_source,
            "Oboz Show": oboz.make_source,
            "Lux FM Stars": luxfm.make_source,
            "Viva Stars": viva.make_source,
            "Concert.ua Concerts": concert_ua.make_source,
            "Karabas Concerts": karabas.make_source,
            "Kontramarka Concerts": kontramarka.make_source,
            "TicketsBox Events": ticketsbox.make_source,
            "ICTV Fakty Entertainment": ictv_fakty.make_source,
            "Novyny LIVE Showbiz": novyny_live.make_source,
            "RBC Ukraine Lite": rbc_lite.make_source,
            "Clutch Showbiz": clutch.make_source,
            "Glavred Stars": glavred.make_source,
            "1plus1 Star Life": one_plus_one.make_star_life_source,
            "1plus1 Show": one_plus_one.make_show_source,
            "Tabloid Pravda": tabloid_pravda.make_source,
            "NV Life Celebrities": nv_life.make_source,
            "Insider UA": insider_ua.make_source,
            "UKR.NET Show Business": ukrnet_showbiz.make_source,
            "Novyny LIVE Stars": novyny_live_stars.make_source,
            "Zirky Showbiz": zirki.make_source,
            "Odna Hvylyna Showbiz": odna_hvylyna.make_source,
        }
        sources = []
        for name, row in configured.items():
            factory = named_factories.get(name)
            if factory:
                sources.append(factory(self.settings.http_timeout_seconds, self.settings.user_agent))
            else:
                sources.append(
                    build_generic_source(
                        SourceConfig(name=row["name"], base_url=row["base_url"], type=row["type"]),
                        timeout=self.settings.http_timeout_seconds,
                        user_agent=self.settings.user_agent,
                    )
                )
        if self.settings.enable_instagram:
            sources.append(
                InstagramSource(
                    SourceConfig(
                        name="Instagram Social",
                        base_url="https://www.instagram.com/",
                        type="social_instagram",
                    ),
                    timeout=self.settings.http_timeout_seconds,
                    user_agent=self.settings.user_agent,
                    export_dir=self.settings.instagram_export_dir,
                    feed_url=self.settings.instagram_feed_url,
                    handles=self._instagram_handles(),
                )
            )
        return sources

    def _is_too_old_for_publishing(self, item) -> bool:
        if self.settings.max_item_age_hours <= 0:
            return False
        if item.category == "concerts":
            return False
        if item.published_at is None:
            return self.settings.require_published_at_for_freshness
        published_at = item.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        age_seconds = (datetime.now(UTC) - published_at.astimezone(UTC)).total_seconds()
        return age_seconds > self.settings.max_item_age_hours * 3600

    def _instagram_handles(self) -> dict[str, str]:
        try:
            payload = json.loads(self.settings.instagram_handles_json)
        except json.JSONDecodeError:
            return {}
        return {str(key): str(value) for key, value in payload.items()} if isinstance(payload, dict) else {}


async def run_forever(settings: Settings, db: Database) -> None:
    runner = SourceRunner(settings, db)
    async def scan_loop() -> None:
        while True:
            stats = await runner.run_once(publish_queue=False)
            log.info(
                "scan_completed",
                scanned_sources=stats.scanned_sources,
                discovered=stats.discovered_count,
                relevant=stats.relevant_count,
                published=stats.published_count,
                errors=stats.error_count,
            )
            await asyncio.sleep(settings.scan_interval_minutes * 60)

    async def publish_loop() -> None:
        while True:
            published = await runner.publish_ready_once()
            if published == 0:
                await asyncio.sleep(5)

    await asyncio.gather(scan_loop(), publish_loop())
