from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="Glavred Stars",
            base_url="https://stars.glavred.info/",
            selectors={
                "article": "article, .article, .news-item, .item, .card",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .description, .announce",
            },
            extra={"limit": 35},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

