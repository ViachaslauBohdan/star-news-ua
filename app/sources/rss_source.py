from __future__ import annotations

import feedparser

from app.models import RawItem
from app.sources.base import BaseSource, SourceConfig
from app.utils.dates import parse_date
from app.utils.text import compact_whitespace
from app.utils.urls import absolute_url, is_probable_image_url


class RSSSource(BaseSource):
    def __init__(self, config: SourceConfig, timeout: int = 15, user_agent: str = "UAStarsMoneyBot/1.0"):
        super().__init__(config, timeout, user_agent)

    def fetch_items(self) -> list[RawItem]:
        response = self.get(self.config.base_url)
        feed = feedparser.parse(response.text)
        items: list[RawItem] = []
        for entry in feed.entries[: self.config.extra.get("limit", 30)]:
            url = absolute_url(self.config.base_url, entry.get("link", ""))
            snippet = compact_whitespace(entry.get("summary", ""))
            image_url = self._entry_image_url(entry, url)
            if not image_url and snippet:
                image_url = self.extract_image_url(self.soup_from_html(snippet))
            published_at = parse_date(entry.get("published") or entry.get("updated"))
            if self.config.extra.get("fetch_article_metadata", True) and (not image_url or not published_at):
                metadata = self.extract_page_metadata(url)
                image_url = image_url or metadata.get("image_url") or ""
                published_at = published_at or metadata.get("published_at")
            items.append(
                RawItem(
                    source_name=self.config.name,
                    source_url=self.config.base_url,
                    title=compact_whitespace(entry.get("title", "")),
                    url=url,
                    published_at=published_at,
                    snippet=snippet,
                    metadata={"image_url": image_url} if image_url else {},
                )
            )
        return [item for item in items if item.title and item.url]

    def _entry_image_url(self, entry, article_url: str) -> str:
        candidates: list[str] = []
        for field in ("media_content", "media_thumbnail"):
            for media in entry.get(field, []) or []:
                if isinstance(media, dict):
                    candidates.append(media.get("url") or "")
        image = entry.get("image")
        if isinstance(image, dict):
            candidates.append(image.get("href") or image.get("url") or "")
        elif isinstance(image, str):
            candidates.append(image)
        for link in entry.get("links", []) or []:
            if not isinstance(link, dict):
                continue
            if link.get("rel") in {"enclosure", "image"} or str(link.get("type", "")).startswith("image/"):
                candidates.append(link.get("href") or "")
        for candidate in candidates:
            image_url = absolute_url(article_url or self.config.base_url, candidate.strip())
            if is_probable_image_url(image_url):
                return image_url
        return ""
