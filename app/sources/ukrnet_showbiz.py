from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="UKR.NET Show Business",
            base_url="https://www.ukr.net/news/show_business.html",
            selectors={
                "article": "article, .im-tl, .news, .item, li",
                "title": "a, h2, h3, .title",
                "link": "a",
                "snippet": "p, .description, .source, .announce",
            },
            extra={"limit": 60},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

