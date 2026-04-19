from __future__ import annotations

import html

from app.models import NormalizedItem, RewriteResult
from app.utils.text import truncate


class TelegramFormatter:
    def format_post(self, item: NormalizedItem, rewrite: RewriteResult) -> str:
        hashtags = " ".join(self._safe_hashtags(rewrite.hashtags))
        body = html.escape(rewrite.text)
        source = html.escape(item.source_name)
        url = html.escape(item.url, quote=True)
        text = (
            f"🔥 <b>{html.escape(rewrite.hook)}</b>\n\n"
            f"{body}\n\n"
            f"Джерело: {source}\n"
            f'Читати: <a href="{url}">відкрити матеріал</a>\n\n'
            f"{hashtags}\n\n"
            "Підпишись, якщо стежиш за українськими зірками"
        )
        return truncate(text, 3900, suffix="...")

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
