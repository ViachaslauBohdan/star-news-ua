from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="Oboz Show",
            base_url="https://www.obozrevatel.com/ukr/shou-oboz/",
            selectors={
                "article": "article, .news-item, .publication, .item-news",
                "title": "a, h2, h3, .news-item__title",
                "link": "a",
                "snippet": "p, .news-item__text, .announce",
            },
            extra={"limit": 30},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

