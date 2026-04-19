from pathlib import Path

from app.db import Database


def test_seeded_sources_include_priority_and_scan_high_priority_first(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.migrate()
    db.seed_defaults()

    sources = db.get_enabled_sources()
    priorities = [row["priority"] for row in sources]
    concert = db.source_metadata_by_name("Concert.ua Concerts")

    assert priorities == sorted(priorities, reverse=True)
    assert concert is not None
    assert concert["credibility_score"] >= 80
    assert concert["entertainment_bias_score"] >= 90

