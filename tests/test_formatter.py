from app.models import NormalizedItem, RewriteResult
from app.services.formatter import TelegramFormatter


def test_formatter_escapes_html_and_adds_source_link() -> None:
    item = NormalizedItem(
        source_id=1,
        source_name="Source <Test>",
        title="Title",
        url="https://example.com/news?a=1&b=2",
        canonical_url="https://example.com/news",
        raw_snippet="snippet",
        matched_entities=["Okean Elzy"],
        category="releases",
        fingerprint="abc",
        similarity_key="title",
        relevance_score=90,
    )
    rewrite = RewriteResult(
        hook="Hook <hot>",
        text="Body & details",
        short_title="Short",
        hashtags=["#OkeanElzy", "#releases"],
    )

    text = TelegramFormatter().format_post(item, rewrite)

    assert "&lt;hot&gt;" in text
    assert "Source &lt;Test&gt;" in text
    assert "https://example.com/news?a=1&amp;b=2" in text
    assert "#OkeanElzy #releases" in text
    assert "Джерело:" in text
