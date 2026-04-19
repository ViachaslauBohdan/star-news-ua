from pathlib import Path

from app.db import Database
from app.models import NormalizedItem
from app.services.dedup import DedupService


def make_item(title: str, url: str, fingerprint: str) -> NormalizedItem:
    return NormalizedItem(
        source_id=None,
        source_name="Test",
        title=title,
        url=url,
        canonical_url=url,
        raw_snippet="snippet",
        matched_entities=["Jerry Heil"],
        category="social",
        fingerprint=fingerprint,
        similarity_key=title.casefold(),
        relevance_score=90,
    )


def test_exact_fingerprint_duplicate(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.migrate()
    item = make_item("Jerry Heil показала нове фото", "https://example.com/a", "same")
    db.insert_discovered_item(item)

    duplicate, reason = DedupService(db).is_duplicate(item)

    assert duplicate is True
    assert reason == "fingerprint"


def test_fuzzy_duplicate(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.migrate()
    db.insert_discovered_item(make_item("Jerry Heil показала нове фото", "https://example.com/a", "a"))

    incoming = make_item("Jerry Heil показала нові фото", "https://example.com/b", "b")
    duplicate, reason = DedupService(db, fuzzy_threshold=80).is_duplicate(incoming)

    assert duplicate is True
    assert reason is not None
    assert reason.startswith("fuzzy:")


def test_duplicate_group_id_for_fuzzy_match(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.migrate()
    original_id = db.insert_discovered_item(
        make_item("YAKTAK оголосив концерт у Києві", "https://example.com/a", "a")
    )

    incoming = make_item("YAKTAK анонсував концерт у Києві", "https://example.com/b", "b")
    result = DedupService(db, fuzzy_threshold=70).check_duplicate(incoming)

    assert result.is_duplicate is True
    assert result.duplicate_group_id == original_id
    assert result.reason is not None
    assert result.reason.startswith("fuzzy:")
