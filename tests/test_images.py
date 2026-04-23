from app.models import NormalizedItem, RawItem, RelevanceResult
from app.services.extractor import Extractor
from app.services.publisher import Publisher
from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource
from app.sources.rss_source import RSSSource
from app.telegram.bot_client import TelegramBotClient


def test_html_source_extracts_card_image() -> None:
    source = HTMLSource(SourceConfig(name="Test", base_url="https://example.com", selectors={}))
    soup = source.soup_from_html(
        """
        <article>
          <a href="/story">Зіркова новина</a>
          <img src="/photo.webp">
          <p>Опис новини</p>
        </article>
        """
    )
    node = soup.select_one("article")

    assert source.extract_image_url(node) == "https://example.com/photo.webp"


def test_html_source_extracts_article_meta_image() -> None:
    source = HTMLSource(SourceConfig(name="Test", base_url="https://example.com", selectors={}))
    soup = source.soup_from_html(
        """
        <html>
          <head>
            <meta property="og:image" content="/images/main.jpg">
          </head>
        </html>
        """
    )

    assert source.extract_meta_image_url(soup, "https://example.com/news/story") == "https://example.com/images/main.jpg"


def test_html_source_extracts_article_meta_description() -> None:
    source = HTMLSource(SourceConfig(name="Test", base_url="https://example.com", selectors={}))
    soup = source.soup_from_html(
        """
        <html>
          <head>
            <meta property="og:description" content="Формальна письмова процедура запущена.">
          </head>
        </html>
        """
    )

    assert source.extract_meta_description(soup) == "Формальна письмова процедура запущена."


def test_html_source_extracts_article_published_time() -> None:
    source = HTMLSource(SourceConfig(name="Test", base_url="https://example.com", selectors={}))
    soup = source.soup_from_html(
        """
        <html>
          <head>
            <meta property="article:published_time" content="2026-04-18T12:21:00+03:00">
          </head>
        </html>
        """
    )

    published_at = source.extract_meta_published_at(soup)

    assert published_at is not None
    assert published_at.isoformat() == "2026-04-18T12:21:00+03:00"


def test_rss_source_extracts_media_image() -> None:
    source = RSSSource(SourceConfig(name="RSS", base_url="https://example.com/rss", selectors={}))
    entry = {"media_content": [{"url": "https://cdn.example.com/main.png"}]}

    assert source._entry_image_url(entry, "https://example.com/story") == "https://cdn.example.com/main.png"


def test_rss_source_extracts_enclosure_image() -> None:
    source = RSSSource(SourceConfig(name="RSS", base_url="https://example.com/rss", selectors={}))
    entry = {"links": [{"rel": "enclosure", "type": "image/jpeg", "href": "/main.jpeg"}]}

    assert source._entry_image_url(entry, "https://example.com/story") == "https://example.com/main.jpeg"


def test_extractor_persists_image_marker() -> None:
    item = Extractor().normalize(
        RawItem(
            source_name="Test",
            source_url="https://example.com",
            title="NK показала новий образ",
            url="https://example.com/story",
            raw_body="body",
            metadata={"image_url": "https://example.com/photo.jpg"},
        ),
        source_id=1,
        relevance=RelevanceResult(is_relevant=True, matched_entities=["NK"], main_entity="NK", category="lifestyle"),
    )

    assert "image_url=https://example.com/photo.jpg" in item.raw_body


def test_publisher_reads_image_marker() -> None:
    item = NormalizedItem(
        source_id=1,
        source_name="Test",
        title="Title",
        url="https://example.com/story",
        canonical_url="https://example.com/story",
        raw_body="body\nimage_url=https://example.com/photo.jpg",
        matched_entities=["NK"],
        category="lifestyle",
        fingerprint="abc",
        similarity_key="title",
    )

    publisher = object.__new__(Publisher)

    assert publisher._image_url(item, None) == "https://example.com/photo.jpg"


def test_photo_caption_keeps_source_link_when_truncated() -> None:
    caption = TelegramBotClient("", dry_run=True)._photo_caption("А" * 2000, "https://example.com/story")

    assert len(caption) <= 1024
    assert "Читати джерело" in caption
