from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource


def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="Odna Hvylyna Showbiz",
            base_url="https://odnaminyta.com/shou-biznes",
            selectors={
                "article": "article, .post, .news-item, .item, .card, li",
                "title": "a, h2, h3, .title, .entry-title",
                "link": "a",
                "snippet": "p, .description, .excerpt, .entry-summary",
            },
            extra={"limit": 45},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

