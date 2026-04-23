from __future__ import annotations

import asyncio
import json
import time
from http import HTTPStatus
from typing import Any

import structlog

from app.config import get_settings
from app.db import Database
from app.logging_config import configure_logging
from app.services.source_runner import SourceRunner

log = structlog.get_logger()


def _header(request: Any, key: str) -> str:
    headers = getattr(request, "headers", {}) or {}
    if hasattr(headers, "get"):
        return str(headers.get(key, ""))
    return str(headers[key]) if key in headers else ""


def _json(payload: dict[str, Any], status_code: int = 200) -> tuple[str, int, dict[str, str]]:
    return (json.dumps(payload, ensure_ascii=False), status_code, {"content-type": "application/json; charset=utf-8"})


async def _run_once() -> dict[str, Any]:
    settings = get_settings()
    configure_logging(settings.log_level)
    db = Database(settings.db_path, database_url=settings.database_url)
    db.migrate()
    db.seed_defaults(settings.app_profile, enable_telethon_sources=settings.enable_telethon_sources)
    stats = await SourceRunner(settings, db).run_once()
    return {
        "ok": True,
        "scanned_sources": stats.scanned_sources,
        "discovered_count": stats.discovered_count,
        "relevant_count": stats.relevant_count,
        "published_count": stats.published_count,
        "error_count": stats.error_count,
        "notes": stats.notes or [],
    }


def handler(request: Any):
    settings = get_settings()
    configure_logging(settings.log_level)
    method = str(getattr(request, "method", "GET")).upper()
    if method not in {"GET", "POST"}:
        return _json({"ok": False, "error": "method_not_allowed"}, HTTPStatus.METHOD_NOT_ALLOWED)
    if settings.cron_secret:
        auth = _header(request, "authorization")
        expected = f"Bearer {settings.cron_secret}"
        if auth != expected:
            log.warning("cron_unauthorized", method=method)
            return _json({"ok": False, "error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
    started = time.monotonic()
    try:
        payload = asyncio.run(_run_once())
        payload["duration_ms"] = int((time.monotonic() - started) * 1000)
        log.info(
            "cron_completed",
            duration_ms=payload["duration_ms"],
            scanned_sources=payload["scanned_sources"],
            discovered_count=payload["discovered_count"],
            relevant_count=payload["relevant_count"],
            published_count=payload["published_count"],
            error_count=payload["error_count"],
        )
        return _json(payload, HTTPStatus.OK)
    except Exception as exc:  # pragma: no cover
        duration_ms = int((time.monotonic() - started) * 1000)
        log.exception("cron_failed", duration_ms=duration_ms, error=str(exc))
        return _json({"ok": False, "error": str(exc), "duration_ms": duration_ms}, HTTPStatus.INTERNAL_SERVER_ERROR)
