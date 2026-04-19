from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="Insider UA",
            base_url="https://insider.ua/",
            selectors={
                "article": "article, .post, .item, .card, .news-item, li",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .description, .excerpt, .lead",
            },
            extra={"limit": 45},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

