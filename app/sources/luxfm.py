from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="Lux FM Stars",
            base_url="https://lux.fm/stars_t25",
            selectors={
                "article": "article, .news-list__item, .news-card, .feed-item",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .description, .text",
            },
            extra={"limit": 30},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

