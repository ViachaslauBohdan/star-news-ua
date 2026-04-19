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
            if title and url:
                items.append(
                    RawItem(
                        source_name=self.config.name,
                        source_url=self.config.base_url,
                        title=compact_whitespace(title),
                        url=url,
                        snippet=snippet,
                    )
                )
        return items

