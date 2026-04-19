from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="UNIAN Lite Stars",
            base_url="https://www.unian.ua/lite/stars",
            selectors={
                "article": "article, .list-thumbs__item, .news-card, .item",
                "title": "a, .list-thumbs__title, h2, h3",
                "link": "a",
                "snippet": "p, .list-thumbs__text, .announce",
            },
            extra={"limit": 30},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

