from __future__ import annotations

from app.models import RawItem
from app.sources.base import BaseSource
from app.utils.text import compact_whitespace


class HTMLSource(BaseSource):
    """Generic selector-based HTML listing source."""

    def fetch_items(self) -> list[RawItem]:
        selectors = self.config.selectors
        article_selector = selectors.get("article", "article")
        title_selector = selectors.get("title", "a")
        link_selector = selectors.get("link", title_selector)
        snippet_selector = selectors.get("snippet", "p")
        soup = self.soup()
        items: list[RawItem] = []
        for node in soup.select(article_selector)[: self.config.extra.get("limit", 30)]:
            title = self.extract_text(node, title_selector)
            url = self.extract_href(node, link_selector)
            snippet = self.extract_text(node, snippet_selector)
            image_url = self.extract_image_url(node)
            published_at = None
            if self.config.extra.get("fetch_article_metadata", True):
                metadata = self.extract_page_metadata(url)
                snippet = snippet or metadata.get("description") or ""
                image_url = image_url or metadata.get("image_url") or ""
                published_at = metadata.get("published_at")
            if title and url:
                items.append(
                    RawItem(
                        source_name=self.config.name,
                        source_url=self.config.base_url,
                        title=compact_whitespace(title),
                        url=url,
                        published_at=published_at,
                        snippet=snippet,
                        metadata={"image_url": image_url} if image_url else {},
                    )
                )
        if items:
            return items
        return self._fallback_link_items(soup)

    def _fallback_link_items(self, soup) -> list[RawItem]:
        items: list[RawItem] = []
        seen: set[str] = set()
        for anchor in soup.select("a[href]")[:300]:
            title = compact_whitespace(anchor.get_text(" ", strip=True))
            url = self.extract_href(anchor, None)
            if not self._looks_like_story_link(title, url) or url in seen:
                continue
            seen.add(url)
            image_url = ""
            published_at = None
            if self.config.extra.get("fetch_article_metadata", True):
                metadata = self.extract_page_metadata(url)
                snippet = metadata.get("description") or ""
                image_url = metadata.get("image_url") or ""
                published_at = metadata.get("published_at")
            items.append(
                RawItem(
                    source_name=self.config.name,
                    source_url=self.config.base_url,
                    title=title,
                    url=url,
                    published_at=published_at,
                    snippet=snippet,
                    metadata={"image_url": image_url} if image_url else {},
                )
            )
            if len(items) >= self.config.extra.get("limit", 30):
                break
        return items

    def _looks_like_story_link(self, title: str, url: str) -> bool:
        if len(title) < 24 or len(title.split()) < 4:
            return False
        blocked_titles = {
            "новини",
            "політика",
            "економіка",
            "спорт",
            "шоу-бізнес",
            "підписатися",
            "реклама",
            "архів",
        }
        if title.strip().casefold() in blocked_titles:
            return False
        blocked_url_parts = ("/tag/", "/tags/", "/author/", "/search", "/weather", "#", "mailto:")
        return not any(part in url for part in blocked_url_parts)
