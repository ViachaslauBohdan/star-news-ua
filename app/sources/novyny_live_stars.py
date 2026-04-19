from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="Novyny LIVE Stars",
            base_url="https://novyny.live/zirki",
            selectors={
                "article": "article, .news-card, .category-news-item, .item, .card",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .description, .text, .excerpt",
            },
            extra={"limit": 40},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

