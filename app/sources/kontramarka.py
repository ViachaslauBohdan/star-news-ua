from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.ticket_source import TicketListingSource


def make_source(timeout: int, user_agent: str) -> TicketListingSource:
    return TicketListingSource(
        SourceConfig(
            name="Kontramarka Concerts",
            base_url="https://kontramarka.ua/uk/concert",
            type="ticket_html",
            selectors={"event_link": "a[href]"},
            extra={"limit": 100},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

