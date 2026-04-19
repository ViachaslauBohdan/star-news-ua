from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource
from app.sources.rss_source import RSSSource
from app.sources.ticket_source import TicketListingSource


def build_generic_source(config: SourceConfig, timeout: int, user_agent: str):
    if config.type == "rss":
        return RSSSource(config, timeout=timeout, user_agent=user_agent)
    if config.type == "ticket_html":
        return TicketListingSource(config, timeout=timeout, user_agent=user_agent)
    return HTMLSource(config, timeout=timeout, user_agent=user_agent)
