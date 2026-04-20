from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.models import NormalizedItem
from app.services.source_runner import SourceRunner


def make_item(published_at: datetime | None, category: str = "lifestyle") -> NormalizedItem:
    return NormalizedItem(
        source_name="Test Stars",
        title="Зіркова новина",
        url="https://example.com/story",
        canonical_url="https://example.com/story",
        published_at=published_at,
        raw_snippet="snippet",
        matched_entities=["NK"],
        category=category,
        fingerprint="fresh",
        similarity_key="fresh",
    )


def runner_with_freshness(hours: int = 24, require_date: bool = False) -> SourceRunner:
    runner = object.__new__(SourceRunner)
    runner.settings = Settings(
        dry_run=True,
        auto_publish=False,
        max_item_age_hours=hours,
        require_published_at_for_freshness=require_date,
    )
    return runner


def test_stars_item_older_than_freshness_window_is_rejected() -> None:
    runner = runner_with_freshness(24)
    item = make_item(datetime.now(UTC) - timedelta(hours=30))

    assert runner._is_too_old_for_publishing(item) is True


def test_concert_items_are_not_rejected_by_article_freshness() -> None:
    runner = runner_with_freshness(24)
    item = make_item(datetime.now(UTC) - timedelta(days=7), category="concerts")

    assert runner._is_too_old_for_publishing(item) is False


def test_missing_published_at_can_be_allowed_for_sources_without_dates() -> None:
    runner = runner_with_freshness(24, require_date=False)

    assert runner._is_too_old_for_publishing(make_item(None)) is False


def test_news_profile_uses_shorter_freshness_window() -> None:
    runner = runner_with_freshness(6)
    item = make_item(datetime.now(UTC) - timedelta(hours=7), category="politics")

    assert runner._is_too_old_for_publishing(item) is True
