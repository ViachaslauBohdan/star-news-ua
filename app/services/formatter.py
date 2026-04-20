from __future__ import annotations

import html

from app.models import NormalizedItem, RewriteResult
from app.services.news_format import sanitize_news_copy


class TelegramFormatter:
    def __init__(self, content_scope: str = "stars"):
        self.content_scope = content_scope

    def format_post(self, item: NormalizedItem, rewrite: RewriteResult) -> str:
        text = rewrite.text
        if self.content_scope in {"ukraine_news", "stars"}:
            text = sanitize_news_copy(text)
            if len(text) <= 3900:
                return text
            return text[:3897].rstrip() + "..."
        escaped = html.escape(text)
        if len(escaped) <= 3900:
            return escaped
        return escaped[:3897].rstrip() + "..."

    def format_ad_slot(self) -> str:
        return (
            "Рекламний слот відкритий.\n\n"
            "Інтеграції, афіші, релізи та партнерські розміщення: напишіть адміністратору каналу."
        )

    def _safe_hashtags(self, hashtags: list[str]) -> list[str]:
        safe = []
        for tag in hashtags[:3]:
            clean = tag.strip()
            if not clean:
                continue
            safe.append(clean if clean.startswith("#") else f"#{clean}")
        return safe

    def _cta(self) -> str:
        if self.content_scope == "ukraine_news":
            return "Більше коротких оновлень — @topnewsuaUKR"
        return "Більше зіркових історій — @uastarsnews"
