from app.models import RawItem, TrackedEntity
from app.services.relevance import RelevanceEngine


def test_relevance_matches_alias_and_category() -> None:
    engine = RelevanceEngine(
        [
            TrackedEntity(
                name="Tina Karol",
                aliases=["Тіна Кароль", "Тина Кароль"],
            )
        ],
        threshold=60,
    )

    result = engine.analyze(
        RawItem(
            source_name="Test",
            source_url="https://example.com",
            title="Тіна Кароль оголосила великий концерт",
            url="https://example.com/news",
            snippet="Співачка готує новий виступ для фанів.",
        )
    )

    assert result.is_relevant is True
    assert result.main_entity == "Tina Karol"
    assert result.category == "concerts"
    assert result.relevance_score >= 60


def test_relevance_rejects_untracked_general_news() -> None:
    engine = RelevanceEngine([TrackedEntity(name="Jerry Heil", aliases=["Джеррі Хейл"])], threshold=60)

    result = engine.analyze(
        RawItem(
            source_name="Test",
            source_url="https://example.com",
            title="Новини економіки України",
            url="https://example.com/news",
            snippet="Загальний огляд без шоу-бізнесу.",
        )
    )

    assert result.is_relevant is False
    assert result.relevance_score == 0


def test_ticket_source_match_is_classified_as_concert() -> None:
    engine = RelevanceEngine([TrackedEntity(name="YAKTAK", aliases=["YAKTAK", "Яктак"])], threshold=60)

    result = engine.analyze(
        RawItem(
            source_name="Tickets",
            source_url="https://example.com",
            title="YAKTAK 29.08 Київ Atlas 800-3000 ₴",
            url="https://example.com/event",
            snippet="YAKTAK 29.08 Київ Atlas 800-3000 ₴",
            metadata={"source_kind": "ticket", "category_hint": "concerts"},
        )
    )

    assert result.is_relevant is True
    assert result.category == "concerts"
    assert result.relevance_score >= 80


def test_new_artist_alias_matching_latin_and_cyrillic() -> None:
    engine = RelevanceEngine(
        [
            TrackedEntity(
                name="Max Barskih",
                aliases=["Max Barskih", "Макс Барських", "Макс Барских"],
            )
        ],
        threshold=60,
    )

    result = engine.analyze(
        RawItem(
            source_name="Test",
            source_url="https://example.com",
            title="Макс Барських анонсував великий тур",
            url="https://example.com/max-barskih-tour",
            snippet="Артист готує серію концертів для фанів.",
        )
    )

    assert result.is_relevant is True
    assert result.main_entity == "Max Barskih"
    assert result.category == "concerts"


def test_turkey_politics_is_not_classified_as_concert() -> None:
    engine = RelevanceEngine([], threshold=60, content_scope="ukraine_news")

    result = engine.analyze(
        RawItem(
            source_name="TSN",
            source_url="https://example.com",
            title="Переговори з РФ: Україна звернулася до Туреччини за допомогою",
            url="https://example.com/politics",
            snippet="Україна просить дипломатичної підтримки.",
            metadata={"source_priority": 90, "source_credibility": 80},
        )
    )

    assert result.is_relevant is True
    assert result.category == "politics"


def test_short_alias_does_not_match_inside_word() -> None:
    engine = RelevanceEngine([TrackedEntity(name="DOVI", aliases=["DOVI", "Дові", "Дови"])], threshold=60)

    result = engine.analyze(
        RawItem(
            source_name="Test",
            source_url="https://example.com",
            title="Онука Ротару в брендових луках назнімала стильний контент",
            url="https://example.com/fashion",
            snippet="Фото з Парижа.",
        )
    )

    assert result.is_relevant is False
    assert result.matched_entities == []
