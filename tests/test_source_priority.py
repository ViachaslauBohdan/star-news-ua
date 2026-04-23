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



def test_ready_queue_is_fair_across_sources() -> None:
    from app.models import NormalizedItem
    from app.services.source_runner import SourceRunner

    def item(source_name: str, index: int) -> NormalizedItem:
        return NormalizedItem(
            source_name=source_name,
            title=f"Новина {source_name} {index}",
            url=f"https://example.com/{source_name}/{index}",
            canonical_url=f"https://example.com/{source_name}/{index}",
            fingerprint=f"{source_name}-{index}",
            similarity_key=f"{source_name} {index}",
        )

    runner = object.__new__(SourceRunner)
    candidates = [
        (1, item("Ukrainska Pravda News", 1)),
        (2, item("Ukrainska Pravda News", 2)),
        (3, item("Ukrainska Pravda News", 3)),
        (4, item("Liga News", 1)),
        (5, item("RBC Ukraine News", 1)),
    ]

    selected = runner._fair_ready_items(candidates, 3)

    assert [queued.source_name for _id, queued in selected] == [
        "Ukrainska Pravda News",
        "Liga News",
        "RBC Ukraine News",
    ]
