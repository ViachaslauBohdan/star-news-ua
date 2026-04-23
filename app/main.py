from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.db import Database
from app.logging_config import configure_logging
from app.services.analytics import AnalyticsService
from app.services.source_runner import SourceRunner, run_forever


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UA Stars Money Bot")
    parser.add_argument("--env-file", default=None, help="Optional env overlay, for example .env.news")
    parser.add_argument("command", choices=["init-db", "scan-once", "run", "summary"], nargs="?", default="scan-once")
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    settings = get_settings(args.env_file)
    configure_logging(settings.log_level)
    db = Database(settings.db_path, database_url=settings.database_url)
    db.migrate()
    db.seed_defaults(settings.app_profile, enable_telethon_sources=settings.enable_telethon_sources)

    if args.command == "init-db":
        print(f"Database initialized at {settings.db_path}")
        return
    if args.command == "summary":
        print(json.dumps(AnalyticsService(db).summary(), ensure_ascii=False, indent=2))
        return
    if args.command == "run":
        await run_forever(settings, db)
        return

    stats = await SourceRunner(settings, db).run_once()
    print(
        json.dumps(
            {
                "scanned_sources": stats.scanned_sources,
                "discovered_count": stats.discovered_count,
                "relevant_count": stats.relevant_count,
                "published_count": stats.published_count,
                "error_count": stats.error_count,
                "notes": stats.notes or [],
                "source_breakdown": stats.source_breakdown_dict(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
