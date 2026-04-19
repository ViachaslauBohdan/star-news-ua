from __future__ import annotations

import json
from typing import Any

import structlog

from app.models import NormalizedItem, RewriteResult
from app.prompts import REWRITE_SYSTEM_PROMPT, REWRITE_USER_PROMPT
from app.utils.text import hashtagify, truncate

log = structlog.get_logger()


class RewriteService:
    def __init__(self, language: str = "uk", enable_openai: bool = False, api_key: str = "", model: str = "gpt-4o-mini"):
        self.language = language
        self.enable_openai = enable_openai and bool(api_key)
        self.api_key = api_key
        self.model = model

    def rewrite(self, item: NormalizedItem) -> RewriteResult:
        if self.enable_openai:
            try:
                return self._rewrite_with_openai(item)
            except Exception as exc:
                log.warning("openai_rewrite_failed_using_fallback", error=str(exc), url=item.url)
        return self._fallback_rewrite(item)

    def _rewrite_with_openai(self, item: NormalizedItem) -> RewriteResult:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        user_prompt = REWRITE_USER_PROMPT.format(
            language=self.language,
            category=item.category,
            entity=", ".join(item.matched_entities) or "українська зірка",
            source=item.source_name,
            title=item.title,
            snippet=truncate(item.raw_snippet or item.raw_body, 1000),
        )
        response = client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        return self._coerce_result(payload, item)

    def _coerce_result(self, payload: dict[str, Any], item: NormalizedItem) -> RewriteResult:
        hook = truncate(str(payload.get("hook") or item.title), 140)
        text = truncate(str(payload.get("text") or ""), 700)
        hashtags = [str(tag) for tag in payload.get("hashtags", [])][:3]
        if not text:
            return self._fallback_rewrite(item)
        return RewriteResult(
            hook=hook,
            text=text,
            short_title=truncate(str(payload.get("short_title") or item.title), 90),
            hashtags=hashtags or self._default_hashtags(item),
        )

    def _fallback_rewrite(self, item: NormalizedItem) -> RewriteResult:
        entity = item.matched_entities[0] if item.matched_entities else "Україна"
        if item.category == "concerts":
            hook = truncate(f"{entity}: з'явилася актуальна концертна дата", 130)
        elif item.category == "social":
            hook = truncate(f"{entity}: новий допис уже обговорюють", 130)
        elif not item.matched_entities:
            hook = truncate(item.title, 130)
        else:
            hook = truncate(f"{entity}: нова історія, яку вже обговорюють", 130)
        body_source = item.raw_snippet or item.raw_body or item.title
        body = truncate(body_source, 420)
        uncertainty = self._uncertainty_prefix(body)
        closing = (
            "Перевіряємо деталі за квитковим майданчиком: дату, місто та наявність місць."
            if item.category == "concerts"
            else "Без зайвих висновків: фіксуємо тільки те, що повідомляє джерело."
        )
        if item.category == "social":
            closing = "Беремо лише сам допис і реакцію навколо нього без вигаданих деталей."
        text = (
            f"{hook}\n\n"
            f"{uncertainty}{body}\n\n"
            f"{closing}"
        )
        return RewriteResult(
            hook=hook,
            text=truncate(text, 700),
            short_title=truncate(item.title, 90),
            hashtags=self._default_hashtags(item),
        )

    def _default_hashtags(self, item: NormalizedItem) -> list[str]:
        tags = []
        if item.matched_entities:
            tags.append(hashtagify(item.matched_entities[0]))
        tags.append(f"#{item.category}")
        return tags[:3]

    def _uncertainty_prefix(self, text: str) -> str:
        lowered = text.casefold()
        if any(token in lowered for token in ("слух", "здається", "може", "ймовір", "вероят")):
            return "У мережі обговорюють: "
        return ""
