from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="Tabloid Pravda",
            base_url="https://tabloid.pravda.com.ua/",
            selectors={
                "article": "article, .article, .post, .news, .card, .item, li",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .description, .lead, .announce",
            },
            extra={"limit": 45},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

