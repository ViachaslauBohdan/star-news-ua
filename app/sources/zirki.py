from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="Zirky Showbiz",
            base_url="https://zirky.com.ua/category/shoubiznes/",
            selectors={
                "article": "article, .post, .entry, .item, .card, li",
                "title": "a, h2, h3, .entry-title",
                "link": "a",
                "snippet": "p, .entry-summary, .excerpt, .description",
            },
            extra={"limit": 45},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

