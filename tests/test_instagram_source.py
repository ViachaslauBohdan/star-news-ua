import json

from app.sources.base import SourceConfig
from app.sources.social_stubs import InstagramSource


def test_instagram_export_source_maps_post_to_raw_item(tmp_path) -> None:
    export_dir = tmp_path / "instagram"
    export_dir.mkdir()
    (export_dir / "posts.json").write_text(
        json.dumps(
            [
                {
                    "username": "jamalajaaa",
                    "caption": "Новий закулісний момент зі зйомок. Обговорюємо?",
                    "shortcode": "ABC123",
                    "timestamp": "2026-04-19T13:00:00+00:00",
                    "displayUrl": "https://example.com/image.jpg",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    source = InstagramSource(
        SourceConfig(name="Instagram Social", base_url="https://www.instagram.com/", type="social_instagram"),
        export_dir=export_dir,
        handles={"Jamala": "jamalajaaa"},
    )

    items = source.fetch_items()

    assert len(items) == 1
    assert items[0].source_name == "Instagram Social"
    assert items[0].url == "https://www.instagram.com/p/ABC123/"
    assert items[0].metadata["category_hint"] == "social"
    assert items[0].metadata["entity_hint"] == "Jamala"
    assert "Jamala в Instagram" in items[0].title

