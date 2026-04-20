from pathlib import Path

from app.db import Database
from app.models import NormalizedItem, RewriteResult
from app.services.formatter import TelegramFormatter


def test_news_profile_enables_only_general_news_sources(tmp_path: Path) -> None:
    db = Database(tmp_path / "news.db")
    db.migrate()
    db.seed_defaults("news")

    enabled = db.get_enabled_sources()

    assert enabled
    assert all(row["type"] == "news_html" for row in enabled)
    assert {row["name"] for row in enabled} >= {"Ukrainska Pravda News", "Suspilne News", "Babel News"}


def test_news_formatter_does_not_add_old_cta_wrapper() -> None:
    item = NormalizedItem(
        source_name="Suspilne News",
        title="Тестова новина",
        url="https://example.com/news",
        canonical_url="https://example.com/news",
        fingerprint="abc",
        similarity_key="testova novyna",
        category="society",
    )
    rewrite = RewriteResult(
        hook="Головне за хвилину",
        text="Короткий виклад новини.",
        short_title="Тест",
        hashtags=["#Україна", "#society"],
    )

    text = TelegramFormatter(content_scope="ukraine_news").format_post(item, rewrite)

    assert text == "Короткий виклад новини."
    assert "Більше коротких оновлень" not in text
    assert "українськими зірками" not in text
    assert "Підпишись, щоб" not in text
