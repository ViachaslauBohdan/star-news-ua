from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="Viva Stars",
            base_url="https://viva.ua/stars",
            selectors={
                "article": "article, .post, .news-item, .card",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .excerpt, .description",
            },
            extra={"limit": 30},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

