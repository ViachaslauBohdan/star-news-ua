from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="TSN Glamur",
            base_url="https://tsn.ua/glamur",
            selectors={
                "article": "article, .c-card, .news-card, .l-news-list__item",
                "title": "a, h2, h3",
                "link": "a",
                "snippet": "p, .c-card__lead, .news-card__lead",
            },
            extra={"limit": 30},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

