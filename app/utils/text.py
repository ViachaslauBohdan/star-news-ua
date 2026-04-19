from __future__ import annotations

import re
import unicodedata


SPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^\w\sа-яА-ЯіїєґІЇЄҐёЁ-]", re.UNICODE)


def compact_whitespace(value: str | None) -> str:
    return SPACE_RE.sub(" ", value or "").strip()


def normalize_for_match(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = PUNCT_RE.sub(" ", text)
    return compact_whitespace(text)


def truncate(value: str, max_chars: int, suffix: str = "...") -> str:
    value = compact_whitespace(value)
    if len(value) <= max_chars:
        return value
    return value[: max_chars - len(suffix)].rstrip() + suffix


def hashtagify(value: str) -> str:
    text = normalize_for_match(value)
    parts = [part for part in re.split(r"[\s-]+", text) if part]
    return "#" + "".join(part.capitalize() for part in parts[:3])

