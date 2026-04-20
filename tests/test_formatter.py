from app.models import NormalizedItem, RewriteResult
from app.services.formatter import TelegramFormatter


def test_formatter_escapes_html_and_preserves_final_post_layout() -> None:
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
        text="⚡️ Hook <hot>\n\nBody & details\n\n👉 Деталі: https://example.com/news?a=1&b=2\n\n#новини",
        short_title="Short",
        hashtags=["#OkeanElzy", "#releases"],
    )

    text = TelegramFormatter(content_scope="other").format_post(item, rewrite)

    assert "&lt;hot&gt;" in text
    assert "https://example.com/news?a=1&amp;b=2" in text
    assert "\n\n" in text
    assert "#новини" in text
