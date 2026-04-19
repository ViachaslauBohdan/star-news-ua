from __future__ import annotations

import feedparser

from app.models import RawItem
from app.sources.base import BaseSource, SourceConfig
from app.utils.dates import parse_date
from app.utils.text import compact_whitespace
from app.utils.urls import absolute_url


class RSSSource(BaseSource):
    def __init__(self, config: SourceConfig, timeout: int = 15, user_agent: str = "UAStarsMoneyBot/1.0"):
        super().__init__(config, timeout, user_agent)

    def fetch_items(self) -> list[RawItem]:
        response = self.get(self.config.base_url)
        feed = feedparser.parse(response.text)
        items: list[RawItem] = []
        for entry in feed.entries[: self.config.extra.get("limit", 30)]:
            url = absolute_url(self.config.base_url, entry.get("link", ""))
            items.append(
                RawItem(
                    source_name=self.config.name,
                    source_url=self.config.base_url,
                    title=compact_whitespace(entry.get("title", "")),
                    url=url,
                    published_at=parse_date(entry.get("published") or entry.get("updated")),
                    snippet=compact_whitespace(entry.get("summary", "")),
                )
            )
        return [item for item in items if item.title and item.url]

