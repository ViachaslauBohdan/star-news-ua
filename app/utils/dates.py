from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for parser in (_from_iso, _from_rfc2822):
        parsed = parser(value)
        if parsed:
            return parsed
    return None


def _from_iso(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _from_rfc2822(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError, IndexError):
        return None

