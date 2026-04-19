from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="Clutch Showbiz",
            base_url="https://clutch.net.ua/showbiz",
            selectors={
                "article": "article, .post, .item, .news-item, .card",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .description, .announce, .excerpt",
            },
            extra={"limit": 35},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

