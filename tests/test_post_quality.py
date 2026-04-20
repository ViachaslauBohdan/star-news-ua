from app.models import NormalizedItem
from app.services.formatter import TelegramFormatter
from app.services.rewrite import RewriteService


def render(item: NormalizedItem) -> str:
    rewrite = RewriteService(language="uk", content_scope="ukraine_news").rewrite(item)
    return TelegramFormatter(content_scope="ukraine_news").format_post(item, rewrite)


def render_stars(item: NormalizedItem) -> str:
    rewrite = RewriteService(language="uk", content_scope="stars").rewrite(item)
    return TelegramFormatter(content_scope="stars").format_post(item, rewrite)


FORBIDDEN_STAR_PHRASES = (
    "повідомляється",
    "за даними джерела",
    "основні деталі",
    "подаємо без висновків",
    "це вже обговорюють",
    "нова історія",
    "інфопривід у заголовку",
    "історія привернула увагу до",
    "увага на зовнішності, новому фото",
)

BANNED_UA_NEWS_PHRASES = (
    "повідомляється",
    "основні деталі",
    "подаємо рамку",
    "подаємо тільки перевірену рамку",
    "джерело для перевірки",
    "тема набирає увагу",
    "важливо для політичного контексту україни",
    "є короткий опис",
    "деталі уточнюються",
    "очікуємо більше інформації",
    "деталі поки короткі",
    "це може вплинути",
    "ситуація може змінитися",
    "йдеться про",
)


def test_news_fallback_does_not_repeat_title_three_times() -> None:
    title = "У Болгарії - сотні повідомлень про фальсифікації на виборах до парламенту"
    item = NormalizedItem(
        source_name="Ukrainska Pravda News",
        title=title,
        url="https://example.com/news",
        canonical_url="https://example.com/news",
        raw_snippet=f"{title} {title} {title}",
        matched_entities=[],
        category="politics",
        fingerprint="abc",
        similarity_key="bulgaria elections",
    )

    post = render(item)

    assert post.count(title) == 1
    assert post.startswith("❗️<b>")
    assert "</b>" in post.splitlines()[0]
    assert "🔗 Джерело" not in post
    assert '<b><a href="https://t.me/topnewsuaUKR">TOPNEWS UA</a></b>' in post
    assert 'Дивитися в джерелі: <a href="https://example.com/news">Ukrainska Pravda News</a>' in post
    assert post.index("Дивитися в джерелі:") < post.index("TOPNEWS UA")
    assert "https://example.com/news" in post
    assert "#політика" not in post
    assert "як повідомляє джерело" not in post
    assert "без зайвих висновків" not in post
    assert "повідомляється" not in post.casefold()
    assert "джерело для перевірки" not in post.casefold()


def test_ukraine_news_posts_avoid_banned_meta_phrases() -> None:
    item = NormalizedItem(
        source_name="Test News",
        title="Приклад заголовка про подію в Україні",
        url="https://example.com/a",
        canonical_url="https://example.com/a",
        raw_snippet="Короткий опис події одним реченням.",
        matched_entities=[],
        category="world",
        fingerprint="ban01",
        similarity_key="ban",
    )
    post = render(item)
    lower = post.casefold()
    assert not any(p in lower for p in BANNED_UA_NEWS_PHRASES)


def test_ukraine_news_post_includes_footer_and_source_link() -> None:
    item = NormalizedItem(
        source_name="NV",
        title="Тест посилання в пості",
        url="https://example.com/nv/1",
        canonical_url="https://example.com/nv/1",
        raw_snippet="Короткий фрагмент для перевірки.",
        matched_entities=[],
        category="war",
        fingerprint="url1",
        similarity_key="url",
    )
    post = render(item)
    assert '<b><a href="https://t.me/topnewsuaUKR">TOPNEWS UA</a></b>' in post
    assert 'Дивитися в джерелі: <a href="https://example.com/nv/1">NV</a>' in post
    assert post.index("Дивитися в джерелі:") < post.index("TOPNEWS UA")
    assert "INSIDER UA" not in post
    assert "Прислать контент" not in post
    assert "Источник" not in post
    assert "👉 Деталі:" not in post
    assert "https://example.com/nv/1" in post
    assert "#війна" not in post


def test_news_post_uses_strict_short_line_format() -> None:
    item = NormalizedItem(
        source_name="Liga News",
        title="МВФ відклав вимогу щодо ПДВ для ФОПів",
        url="https://example.com/imf",
        canonical_url="https://example.com/imf",
        raw_snippet="МВФ поки відклав вимогу щодо ПДВ для частини підприємців. Рішення обговорювали в межах домовленостей з Україною.",
        matched_entities=[],
        category="economy",
        fingerprint="def",
        similarity_key="imf taxes",
    )

    post = render(item)
    lines = [line for line in post.splitlines() if line.strip()]

    assert 120 <= len(post) <= 420
    assert "<b>" in lines[0]
    assert "🔗 Джерело" not in post
    assert '<b><a href="https://t.me/topnewsuaUKR">TOPNEWS UA</a></b>' in post
    assert 'Дивитися в джерелі: <a href="https://example.com/imf">Liga News</a>' in post
    assert "https://example.com/imf" in post
    assert "#економіка" not in post
    assert "Йдеться про" not in post
    assert all(len(line) <= 140 for line in lines)


def test_ukraine_news_escapes_html_in_source_url_and_title() -> None:
    item = NormalizedItem(
        source_name='Liga <News> & Co',
        title='МВФ <відклав> вимогу & рішення',
        url='https://example.com/a?x=1&y="two"',
        canonical_url="https://example.com/a",
        raw_snippet='Уряд сказав: <без> різких змін & паніки.',
        matched_entities=[],
        category="economy",
        fingerprint="html",
        similarity_key="html",
    )

    post = render(item)

    assert "<відклав>" not in post
    assert "&lt;відклав&gt;" in post
    assert "&lt;News&gt; &amp; Co" in post
    assert 'href="https://example.com/a?x=1&amp;y=&quot;two&quot;"' in post


def test_stars_post_uses_stars_template() -> None:
    item = NormalizedItem(
        source_name="UNIAN Lite Stars",
        title="Олександра Заріцька показала результат схуднення",
        url="https://example.com/kazka",
        canonical_url="https://example.com/kazka",
        raw_snippet="Солістка KAZKA Олександра Заріцька показала нове фото після схуднення. Фани активно обговорюють зміни в її образі.",
        matched_entities=["KAZKA"],
        category="lifestyle",
        fingerprint="ghi",
        similarity_key="kazka photo",
    )

    post = render_stars(item)
    content_lines = [line for line in post.splitlines() if line.strip()]

    assert post.startswith("😳<b>KAZKA: Олександра Заріцька показала результат схуднення</b>")
    assert "💬" not in post
    assert '<b><a href="https://t.me/uastarsnews">UA Stars News</a></b>' in post
    assert 'Дивитися в джерелі: <a href="https://example.com/kazka">UNIAN Lite Stars</a>' in post
    assert "#зірки" not in post
    assert "https://example.com/kazka" in post
    assert 3 <= len(content_lines) <= 6
    assert not any(phrase in post.casefold() for phrase in FORBIDDEN_STAR_PHRASES)


def test_stars_post_uses_concrete_event_instead_of_vague_hook() -> None:
    item = NormalizedItem(
        source_name="UNIAN Lite Stars",
        title="Заріцька схудла і показала прес: як змінилась солістка KAZKA",
        url="https://example.com/zaritska",
        canonical_url="https://example.com/zaritska",
        raw_snippet="Солістка KAZKA показала фото після схуднення. Фани відреагували на зміни в її фігурі.",
        matched_entities=["KAZKA"],
        category="lifestyle",
        fingerprint="look",
        similarity_key="zaritska look",
    )

    post = render_stars(item)
    first_line = post.splitlines()[0]

    assert "схудла" in first_line.casefold()
    assert "показала прес" in first_line.casefold()
    assert "<b>" in first_line
    assert "це вже обговорюють" not in post


def test_stars_post_uses_concert_event_in_first_line() -> None:
    item = NormalizedItem(
        source_name="Concert.ua Concerts",
        title="БЕЗ ОБМЕЖЕНЬ 23 травня 19:00, сб | Київ, Тераса Gulliver від 1600 ₴",
        url="https://example.com/concert",
        canonical_url="https://example.com/concert",
        raw_snippet="БЕЗ ОБМЕЖЕНЬ 23 травня 19:00, сб | Київ, Тераса Gulliver від 1600 ₴",
        matched_entities=["Bez Obmezhen"],
        category="concerts",
        fingerprint="concert",
        similarity_key="bez obmezhen concert",
    )

    post = render_stars(item)
    first_line = post.splitlines()[0]

    assert first_line.startswith("🔥<b>Без Обмежень:")
    assert "23 травня" in first_line
    assert "Київ" in post


def test_stars_llm_json_builds_template_and_sets_image_query() -> None:
    svc = RewriteService(content_scope="stars")
    item = NormalizedItem(
        source_name="Test",
        title="X",
        url="https://ex.com/story",
        canonical_url="https://ex.com/story",
        raw_snippet="",
        matched_entities=["NK"],
        category="lifestyle",
        fingerprint="a",
        similarity_key="k",
    )
    payload = {
        "entity": "Надя Дорофєєва",
        "category": "other",
        "event": "вразила фанів новим треком",
        "text": "Трек набирає оберти.\nФани вже діляться враженнями.",
        "pulse": "Сперечаються, хто крутіший",
        "image_query": "Надя Дорофєєва концерт сцена",
    }
    r = svc._rewrite_result_from_stars_json(payload, item)
    assert r is not None
    assert r.image_query == "Надя Дорофєєва концерт сцена"
    assert "👀<b>Надя Дорофєєва" in r.text
    assert "<b>" in r.text
    assert "💬" not in r.text
    assert '<b><a href="https://t.me/uastarsnews">UA Stars News</a></b>' in r.text
    assert "#зірки" not in r.text


def test_stars_llm_json_clears_image_query_when_scraper_image_present() -> None:
    svc = RewriteService(content_scope="stars")
    item = NormalizedItem(
        source_name="T",
        title="t",
        url="https://ex.com/u",
        canonical_url="https://ex.com/u",
        raw_body="body\nimage_url=https://ex.com/p.jpg",
        raw_snippet="",
        matched_entities=["X"],
        category="other",
        fingerprint="b",
        similarity_key="x",
    )
    payload = {
        "entity": "Х",
        "category": "other",
        "event": "щось сталося",
        "text": "Перше речення. Друге речення.",
        "pulse": None,
        "image_query": "ignored query",
    }
    r = svc._rewrite_result_from_stars_json(payload, item)
    assert r is not None
    assert r.image_query is None


def test_stars_post_empty_snippet_has_no_title_meta_fact_line() -> None:
    item = NormalizedItem(
        source_name="Example Stars",
        title="Тестова зірка зробила заяву в ефірі",
        url="https://example.com/star",
        canonical_url="https://example.com/star",
        raw_snippet="",
        matched_entities=["Test Star"],
        category="society",
        fingerprint="empty",
        similarity_key="empty snippet star",
    )

    post = render_stars(item)

    assert post.startswith("👀<b>Test Star:")
    assert "інфопривід у заголовку" not in post.casefold()
    assert "Дивитися в джерелі:" in post
    assert "#зірки" not in post


def test_rewrite_removes_image_metadata_markers_from_post_text() -> None:
    item = NormalizedItem(
        source_name="TSN News",
        title="В Україні 19 квітня - сильна магнітна буря",
        url="https://example.com/tsn",
        canonical_url="https://example.com/tsn",
        raw_body="image_url=https://img.tsn.ua/cached/photo.jpeg",
        matched_entities=[],
        category="society",
        fingerprint="jkl",
        similarity_key="magnetic storm",
    )

    post = render(item)

    assert "image_url=" not in post
    assert "img.tsn" not in post
    assert "<b>" in post
    assert "🔗 Джерело" not in post
    assert "Йдеться про" not in post
    assert "Дивитися в джерелі:" in post
    assert "https://example.com/tsn" in post
