from __future__ import annotations

from app.constants import (
    CHARITY_KEYWORDS,
    CONCERT_KEYWORDS,
    ECONOMY_KEYWORDS,
    EMERGENCY_KEYWORDS,
    HEALTH_KEYWORDS,
    INTERVIEW_KEYWORDS,
    LIFESTYLE_KEYWORDS,
    MONEY_KEYWORDS,
    POLITICS_KEYWORDS,
    RELEASE_KEYWORDS,
    RELATIONSHIP_KEYWORDS,
    SCANDAL_KEYWORDS,
    SOCIAL_KEYWORDS,
    SPORTS_KEYWORDS,
    TECH_KEYWORDS,
    TV_KEYWORDS,
    WAR_KEYWORDS,
    WORLD_KEYWORDS,
)
from app.models import RawItem, RelevanceResult, TrackedEntity
from app.utils.text import normalize_for_match


class RelevanceEngine:
    def __init__(self, tracked_entities: list[TrackedEntity], threshold: int = 60, content_scope: str = "stars"):
        self.tracked_entities = tracked_entities
        self.threshold = threshold
        self.content_scope = content_scope

    def analyze(self, item: RawItem) -> RelevanceResult:
        haystack = normalize_for_match(" ".join([item.title, item.snippet, item.raw_body]))
        matched: list[str] = []
        reasons: list[str] = []
        for entity in self.tracked_entities:
            aliases = [entity.name, *entity.aliases]
            if any(self._contains_alias(haystack, alias) for alias in aliases):
                matched.append(entity.name)
                reasons.append(f"matched:{entity.name}")

        category = item.metadata.get("category_hint") or self.assign_category(haystack)
        score = self._score(item, matched, category)
        is_aggregator_item = self.content_scope == "ukraine_news" and self._looks_like_news_item(item)
        if is_aggregator_item and not matched:
            score = max(score, self._aggregator_score(item, category))
            reasons.append("scope:ukraine_news")
        return RelevanceResult(
            is_relevant=(bool(matched) or is_aggregator_item) and score >= self.threshold,
            matched_entities=matched,
            main_entity=matched[0] if matched else None,
            category=category,
            relevance_score=score,
            reasons=reasons,
        )

    def assign_category(self, normalized_text: str) -> str:
        checks = [
            ("war", WAR_KEYWORDS),
            ("politics", POLITICS_KEYWORDS),
            ("world", WORLD_KEYWORDS),
            ("emergency", EMERGENCY_KEYWORDS),
            ("scandal", SCANDAL_KEYWORDS),
            ("relationships", RELATIONSHIP_KEYWORDS),
            ("money", MONEY_KEYWORDS),
            ("concerts", CONCERT_KEYWORDS),
            ("social", SOCIAL_KEYWORDS),
            ("releases", RELEASE_KEYWORDS),
            ("charity", CHARITY_KEYWORDS),
            ("tv", TV_KEYWORDS),
            ("economy", ECONOMY_KEYWORDS),
            ("health", HEALTH_KEYWORDS),
            ("tech", TECH_KEYWORDS),
            ("sports", SPORTS_KEYWORDS),
            ("interviews", INTERVIEW_KEYWORDS),
            ("lifestyle", LIFESTYLE_KEYWORDS),
        ]
        for category, keywords in checks:
            if any(keyword in normalized_text for keyword in keywords):
                return category
        return "other"

    def _score(self, item: RawItem, matched: list[str], category: str) -> int:
        if not matched:
            return 0
        score = 55
        title_norm = normalize_for_match(item.title)
        if any(normalize_for_match(name) in title_norm for name in matched):
            score += 25
        if category != "other":
            score += 10
        if item.metadata.get("source_kind") == "ticket":
            score += 15
        if len(matched) > 1:
            score += 5
        if item.snippet or item.raw_body:
            score += 5
        return min(score, 100)

    def _aggregator_score(self, item: RawItem, category: str) -> int:
        priority = int(item.metadata.get("source_priority") or 50)
        credibility = int(item.metadata.get("source_credibility") or 70)
        score = 35 + int(priority * 0.25) + int(credibility * 0.25)
        if category != "other":
            score += 10
        if item.snippet:
            score += 5
        return min(score, 100)

    def _looks_like_news_item(self, item: RawItem) -> bool:
        title = normalize_for_match(item.title)
        if len(title) < 18:
            return False
        blocked = ("погода", "гороскоп", "реклама", "тест", "кросворд", "привітання")
        return not any(token in title for token in blocked)

    def _contains_alias(self, haystack: str, alias: str) -> bool:
        normalized_alias = normalize_for_match(alias)
        if not normalized_alias:
            return False
        return normalized_alias in haystack
