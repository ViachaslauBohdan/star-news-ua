from __future__ import annotations

import re

from app.models import RawItem
from app.sources.base import BaseSource
from app.utils.text import compact_whitespace
from app.utils.urls import absolute_url


PRICE_OR_DATE_RE = re.compile(
    r"(\d{1,2}[./]\d{1,2}|\d{1,2}\s+[а-яіїєґa-z]+|₴|uah|грн|квитк|buy|tickets?)",
    re.IGNORECASE,
)


class TicketListingSource(BaseSource):
    """Extract event-like links from ticket marketplaces."""

    def fetch_items(self) -> list[RawItem]:
        soup = self.soup()
        items: list[RawItem] = []
        seen_urls: set[str] = set()
        limit = int(self.config.extra.get("limit", 80))
        for link in soup.select(self.config.selectors.get("event_link", "a[href]")):
            title = compact_whitespace(link.get_text(" ", strip=True))
            href = link.get("href") or ""
            url = absolute_url(self.config.base_url, href)
            if not self._looks_like_event(title, url) or url in seen_urls:
                continue
            seen_urls.add(url)
            items.append(
                RawItem(
                    source_name=self.config.name,
                    source_url=self.config.base_url,
                    title=title,
                    url=url,
                    snippet=title,
                    metadata={"source_kind": "ticket", "category_hint": "concerts"},
                )
            )
            if len(items) >= limit:
                break
        return items

    def _looks_like_event(self, title: str, url: str) -> bool:
        if len(title) < 8:
            return False
        lowered_url = url.casefold()
        if any(skip in lowered_url for skip in ("login", "help", "offer", "privacy", "payment", "delivery")):
            return False
        return bool(PRICE_OR_DATE_RE.search(title)) or any(
            token in lowered_url for token in ("concert", "event", "tickets", "kvit", "afisha")
        )

