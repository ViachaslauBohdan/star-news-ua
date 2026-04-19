from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

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
class RunStats:
    scanned_sources: int = 0
    discovered_count: int = 0
    relevant_count: int = 0
    published_count: int = 0
    error_count: int = 0
    notes: list[str] | None = None

    def note(self, value: str) -> None:
        if self.notes is None:
            self.notes = []
        self.notes.append(value)


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
        )
        self.publisher = Publisher(settings, db)

    async def run_once(self) -> RunStats:
        run_id = self.db.create_run()
        stats = RunStats()
        try:
            tracked = self.db.get_tracked_entities()
            relevance = RelevanceEngine(
                tracked,
                threshold=self.settings.relevance_threshold,
                content_scope=self.settings.content_scope,
            )
            sources = self._build_sources()
            stats.scanned_sources = len(sources)
            for source in sources:
                raw_items = source.safe_fetch()
                stats.discovered_count += len(raw_items)
                for raw in raw_items:
                    await self._handle_item(raw, relevance, stats)
        except Exception as exc:
            stats.error_count += 1
            stats.note(str(exc))
            log.exception("run_failed", error=str(exc))
        finally:
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
        if not result.is_relevant:
            normalized = self.extractor.normalize(raw, source_id, result)
            self.db.insert_discovered_item(normalized, status=ItemStatus.IRRELEVANT)
            return

        stats.relevant_count += 1
        normalized = self.extractor.normalize(raw, source_id, result)
        duplicate = self.dedup.check_duplicate(normalized)
        if duplicate.is_duplicate:
            normalized.duplicate_group_id = duplicate.duplicate_group_id
            normalized.is_primary_story = False
            item_id = self.db.insert_discovered_item(normalized, status=ItemStatus.DUPLICATE)
            stats.note(f"duplicate:{duplicate.reason}:{raw.url}")
            if item_id is None:
                return
            return

        if self.settings.max_publish_per_run and stats.published_count >= self.settings.max_publish_per_run:
            stats.note(f"publish_cap_reached:{raw.url}")
            return

        item_id = self.db.insert_discovered_item(normalized, status=ItemStatus.READY)
        if item_id is None:
            return
        rewrite = self.rewriter.rewrite(normalized)

        if self.settings.preview_mode or not (self.settings.auto_publish or self.settings.telegram_admin_chat_id):
            log.info("preview_post", title=raw.title, text=rewrite.text)
            return

        if stats.published_count > 0 and self.settings.delayed_publish_seconds:
            await asyncio.sleep(self.settings.delayed_publish_seconds)
        publish_result = await self.publisher.publish(item_id, normalized, rewrite)
        if publish_result.sent or publish_result.dry_run:
            stats.published_count += 1

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

    def _instagram_handles(self) -> dict[str, str]:
        try:
            payload = json.loads(self.settings.instagram_handles_json)
        except json.JSONDecodeError:
            return {}
        return {str(key): str(value) for key, value in payload.items()} if isinstance(payload, dict) else {}


async def run_forever(settings: Settings, db: Database) -> None:
    runner = SourceRunner(settings, db)
    while True:
        stats = await runner.run_once()
        log.info(
            "scan_completed",
            scanned_sources=stats.scanned_sources,
            discovered=stats.discovered_count,
            relevant=stats.relevant_count,
            published=stats.published_count,
            errors=stats.error_count,
        )
        await asyncio.sleep(settings.scan_interval_minutes * 60)
