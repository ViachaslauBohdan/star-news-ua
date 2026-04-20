from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter, TelegramError

from app.models import NormalizedItem
from app.services.formatter import TelegramFormatter
from app.services.rewrite import RewriteService


@dataclass
class ReformatStats:
    scanned: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


ENTERTAINMENT_CATEGORIES = {
    "scandal",
    "relationships",
    "money",
    "concerts",
    "lifestyle",
    "interviews",
    "social",
    "releases",
    "other",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reformat already published Telegram posts.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--content-scope", default=None)
    parser.add_argument("--category", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sleep-seconds", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_rows(db_path: Path, limit: int, category: str | None = None) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT
                pp.id AS published_post_id,
                pp.telegram_message_id,
                pp.telegram_chat_id,
                pp.published_text,
                di.id AS discovered_item_id,
                di.source_id,
                COALESCE(s.name, pp.source_name, '') AS source_name,
                di.title,
                di.url,
                di.canonical_url,
                di.published_at,
                COALESCE(di.raw_snippet, '') AS raw_snippet,
                COALESCE(di.raw_body, '') AS raw_body,
                di.matched_entities_json,
                di.category,
                di.fingerprint,
                di.similarity_key,
                di.primary_entity,
                di.relevance_score,
                COALESCE(di.relevance_explanation, '') AS relevance_explanation,
                di.is_primary_story,
                di.duplicate_group_id
            FROM published_posts pp
            JOIN discovered_items di ON di.id = pp.discovered_item_id
            LEFT JOIN sources s ON s.id = di.source_id
            WHERE pp.telegram_message_id IS NOT NULL
              AND pp.telegram_chat_id IS NOT NULL
        """
        params: list[object] = []
        if category:
            sql += " AND di.category = ?"
            params.append(category)
        sql += " ORDER BY pp.id"
        if limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        return list(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def item_from_row(row: sqlite3.Row) -> NormalizedItem:
    return NormalizedItem(
        source_id=row["source_id"],
        source_name=row["source_name"] or "Українські медіа",
        title=row["title"],
        url=row["url"],
        canonical_url=row["canonical_url"],
        raw_snippet=row["raw_snippet"] or "",
        raw_body=row["raw_body"] or "",
        matched_entities=json.loads(row["matched_entities_json"] or "[]"),
        category=row["category"] or "other",
        fingerprint=row["fingerprint"],
        similarity_key=row["similarity_key"],
        primary_entity=row["primary_entity"],
        relevance_score=int(row["relevance_score"] or 0),
        relevance_explanation=row["relevance_explanation"] or "",
        is_primary_story=bool(row["is_primary_story"]),
        duplicate_group_id=row["duplicate_group_id"],
    )


def should_skip(row: sqlite3.Row, content_scope: str) -> bool:
    if content_scope != "stars":
        return False
    matched_entities = json.loads(row["matched_entities_json"] or "[]")
    if matched_entities:
        return False
    return (row["category"] or "other") not in ENTERTAINMENT_CATEGORIES


def store_updated_text(db_path: Path, published_post_id: int, text: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE published_posts SET published_text = ? WHERE id = ?",
            (text, published_post_id),
        )
        conn.commit()
    finally:
        conn.close()


async def edit_post(bot: Bot, chat_id: str, message_id: int, text: str) -> None:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
            return
        except RetryAfter as exc:
            last_exc = exc
            await asyncio.sleep(float(exc.retry_after) + 1)
        except BadRequest as exc:
            last_exc = exc
            message = str(exc).lower()
            if "message is not modified" in message:
                return
            try:
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=text[:1024],
                    parse_mode=ParseMode.HTML,
                )
                return
            except RetryAfter as retry_exc:
                last_exc = retry_exc
                await asyncio.sleep(float(retry_exc.retry_after) + 1)
    if last_exc:
        raise last_exc


async def main() -> None:
    args = parse_args()
    if args.env_file != ".env":
        load_dotenv(".env", override=False)
    load_dotenv(args.env_file, override=True)

    import os

    db_path = Path(args.db_path or os.environ.get("DB_PATH", "data/app.db"))
    content_scope = args.content_scope or os.environ.get("CONTENT_SCOPE", "stars")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token and not args.dry_run:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required unless --dry-run is used")

    bot = Bot(token=token) if not args.dry_run else None
    rewrite_service = RewriteService(
        language=os.environ.get("APP_LANGUAGE", "uk"),
        content_scope=content_scope,
    )
    formatter = TelegramFormatter(content_scope=content_scope)
    stats = ReformatStats()

    for row in load_rows(db_path, args.limit, args.category):
        stats.scanned += 1
        if should_skip(row, content_scope):
            stats.skipped += 1
            print(f"skip id={row['published_post_id']} category={row['category']} title={row['title'][:70]}")
            continue

        item = item_from_row(row)
        text = formatter.format_post(item, rewrite_service.rewrite(item))
        if text == row["published_text"]:
            stats.skipped += 1
            continue

        if args.dry_run:
            stats.updated += 1
            print(f"dry-run id={row['published_post_id']} message={row['telegram_message_id']} chars={len(text)}")
            continue

        try:
            assert bot is not None
            await edit_post(bot, str(row["telegram_chat_id"]), int(row["telegram_message_id"]), text)
            store_updated_text(db_path, int(row["published_post_id"]), text)
            stats.updated += 1
            print(f"updated id={row['published_post_id']} message={row['telegram_message_id']} chars={len(text)}")
            if args.sleep_seconds > 0:
                await asyncio.sleep(args.sleep_seconds)
        except TelegramError as exc:
            stats.failed += 1
            print(f"failed id={row['published_post_id']} message={row['telegram_message_id']} error={exc}")

    print(
        json.dumps(
            {
                "scanned": stats.scanned,
                "updated": stats.updated,
                "skipped": stats.skipped,
                "failed": stats.failed,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
