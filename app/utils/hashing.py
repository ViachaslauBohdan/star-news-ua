from __future__ import annotations

import hashlib

from app.utils.text import normalize_for_match


def stable_fingerprint(source: str, title: str, canonical_url: str) -> str:
    payload = "|".join([normalize_for_match(source), normalize_for_match(title), canonical_url])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

