from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="ICTV Fakty Entertainment",
            base_url="https://fakty.com.ua/ua/showbiz/",
            selectors={
                "article": "article, .post, .news-item, .card, .content-list__item",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .description, .announce, .excerpt",
            },
            extra={"limit": 35},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

