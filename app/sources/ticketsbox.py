from __future__ import annotations

from app.sources.base import SourceConfig
from app.sources.ticket_source import TicketListingSource


def make_source(timeout: int, user_agent: str) -> TicketListingSource:
    return TicketListingSource(
        SourceConfig(
            name="TicketsBox Events",
            base_url="https://ticketsbox.com/uk/",
            type="ticket_html",
            selectors={"event_link": "a[href]"},
            extra={"limit": 100},
        ),
        timeout=timeout,
        user_agent=user_agent,
    )

