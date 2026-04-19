from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="RBC Ukraine Lite",
            base_url="https://lite.rbc.ua/",
            selectors={
                "article": "article, .newsline__item, .item, .news-feed__item, .card",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .description, .announce",
            },
            extra={"limit": 45},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

