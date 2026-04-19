from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_star_life_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="1plus1 Star Life",
            base_url="https://1plus1.ua/tag/zirkove-zitta",
            selectors={
                "article": "article, .news-card, .card, .item",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .description, .announce",
            },
            extra={"limit": 35},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )


def make_show_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="1plus1 Show",
            base_url="https://1plus1.ua/tag/show",
            selectors={
                "article": "article, .news-card, .card, .item",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .description, .announce",
            },
            extra={"limit": 35},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

