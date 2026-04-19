from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models import RawItem
from app.sources.base import BaseSource, SourceConfig
from app.utils.dates import parse_date
from app.utils.text import compact_whitespace, truncate


class InstagramSource(BaseSource):
    """Instagram ingestion from approved provider JSON or local exports.

    This intentionally avoids login-based scraping. Feed providers can write
    JSON files into ``export_dir`` or expose a JSON endpoint in ``feed_url``.
    Supported item keys include caption/text, url, shortcode, timestamp/date,
    username/ownerUsername, and displayUrl/imageUrl.
    """

    def __init__(
        self,
        config: SourceConfig,
        timeout: int = 15,
        user_agent: str = "UAStarsMoneyBot/1.0",
        export_dir: Path | str = "data/social/instagram",
        feed_url: str = "",
        handles: dict[str, str] | None = None,
    ):
        super().__init__(config, timeout=timeout, user_agent=user_agent)
        self.export_dir = Path(export_dir)
        self.feed_url = feed_url
        self.handles = handles or {}

    def fetch_items(self) -> list[RawItem]:
        payloads = []
        if self.feed_url:
            response = self.get(self.feed_url)
            payloads.extend(self._coerce_payload(response.json()))
        payloads.extend(self._read_export_payloads())
        return [item for item in (self._to_raw_item(payload) for payload in payloads) if item]

    def _read_export_payloads(self) -> list[dict[str, Any]]:
        if not self.export_dir.exists():
            return []
        payloads: list[dict[str, Any]] = []
        for path in sorted(self.export_dir.glob("*.json")):
            try:
                payloads.extend(self._coerce_payload(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError):
                continue
        return payloads

    def _coerce_payload(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("items", "posts", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [payload]
        return []

    def _to_raw_item(self, payload: dict[str, Any]) -> RawItem | None:
        caption = compact_whitespace(
            str(payload.get("caption") or payload.get("text") or payload.get("description") or "")
        )
        username = compact_whitespace(
            str(payload.get("ownerUsername") or payload.get("username") or payload.get("handle") or "")
        ).lstrip("@")
        url = compact_whitespace(str(payload.get("url") or payload.get("permalink") or ""))
        shortcode = compact_whitespace(str(payload.get("shortcode") or payload.get("code") or ""))
        if not url and shortcode:
            url = f"https://www.instagram.com/p/{shortcode}/"
        if not url and username:
            url = f"https://www.instagram.com/{username}/"
        if not caption or not url:
            return None

        entity_name = self._entity_for_username(username)
        title_prefix = f"{entity_name} в Instagram" if entity_name else f"@{username} в Instagram"
        published_at = parse_date(str(payload.get("timestamp") or payload.get("date") or payload.get("createdAt") or ""))
        return RawItem(
            source_name=self.config.name,
            source_url=self.config.base_url,
            title=truncate(f"{title_prefix}: {caption}", 180),
            url=url,
            published_at=published_at,
            snippet=truncate(caption, 600),
            metadata={
                "source_kind": "social",
                "category_hint": "social",
                "platform": "instagram",
                "username": username,
                "entity_hint": entity_name,
                "image_url": payload.get("displayUrl") or payload.get("imageUrl"),
            },
        )

    def _entity_for_username(self, username: str) -> str | None:
        if not username:
            return None
        normalized = username.casefold().lstrip("@")
        for entity, handle in self.handles.items():
            if normalized == str(handle).casefold().lstrip("@"):
                return entity
        return None


class YouTubeSource(BaseSource):
    """Future adapter for YouTube Data API channel/video monitoring."""

    def fetch_items(self) -> list[RawItem]:
        return []


class TikTokSource(BaseSource):
    """Future adapter for a compliant TikTok source/API integration."""

    def fetch_items(self) -> list[RawItem]:
        return []
