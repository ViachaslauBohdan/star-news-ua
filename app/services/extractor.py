from __future__ import annotations

from app.models import NormalizedItem, RawItem, RelevanceResult
from app.utils.hashing import stable_fingerprint
from app.utils.text import normalize_for_match
from app.utils.urls import canonicalize_url


class Extractor:
    def normalize(self, raw: RawItem, source_id: int | None, relevance: RelevanceResult) -> NormalizedItem:
        canonical_url = canonicalize_url(raw.url)
        similarity_key = normalize_for_match(raw.title)
        return NormalizedItem(
            source_id=source_id,
            source_name=raw.source_name,
            title=raw.title,
            url=raw.url,
            canonical_url=canonical_url,
            published_at=raw.published_at,
            raw_snippet=raw.snippet,
            raw_body=raw.raw_body,
            matched_entities=relevance.matched_entities,
            category=relevance.category,
            fingerprint=stable_fingerprint(raw.source_name, raw.title, canonical_url),
            similarity_key=similarity_key,
            primary_entity=relevance.main_entity,
            relevance_score=relevance.relevance_score,
            relevance_explanation="; ".join(relevance.reasons),
            is_primary_story=bool(relevance.main_entity),
        )
