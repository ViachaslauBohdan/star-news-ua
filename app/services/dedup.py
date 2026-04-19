from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from app.db import Database
from app.models import NormalizedItem


@dataclass(slots=True)
class DuplicateCheck:
    is_duplicate: bool
    reason: str | None = None
    duplicate_group_id: int | None = None
    score: float | None = None


class DedupService:
    def __init__(self, db: Database, fuzzy_threshold: int = 88):
        self.db = db
        self.fuzzy_threshold = fuzzy_threshold

    def is_duplicate(self, item: NormalizedItem) -> tuple[bool, str | None]:
        result = self.check_duplicate(item)
        return result.is_duplicate, result.reason

    def check_duplicate(self, item: NormalizedItem) -> DuplicateCheck:
        if self.db.fingerprint_exists(item.fingerprint):
            return DuplicateCheck(True, "fingerprint", self.db.item_id_by_fingerprint(item.fingerprint), 100)
        if self.db.canonical_url_exists(item.canonical_url):
            return DuplicateCheck(True, "canonical_url", self.db.item_id_by_canonical_url(item.canonical_url), 100)
        for existing_id, _title, similarity_key in self.db.recent_similarity_keys():
            score = fuzz.token_set_ratio(item.similarity_key, similarity_key)
            if score >= self.fuzzy_threshold:
                return DuplicateCheck(True, f"fuzzy:{existing_id}:{score}", existing_id, score)
        return DuplicateCheck(False)
