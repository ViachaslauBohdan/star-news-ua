from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="NV Life Celebrities",
            base_url="https://life.nv.ua/ukr/znamenitosti.html",
            selectors={
                "article": "article, .article, .news-item, .card, .item, li",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .description, .announce, .lead",
            },
            extra={"limit": 45},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

