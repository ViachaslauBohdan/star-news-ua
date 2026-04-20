from __future__ import annotations

import json
import html
import re
from typing import Any

import structlog

from app.constants import DEFAULT_TRACKED_ENTITIES
from app.models import NormalizedItem, RewriteResult
from app.prompts import (
    NEWS_REWRITE_SYSTEM_PROMPT,
    NEWS_REWRITE_USER_PROMPT,
    NEWS_SHOTS_UK,
    REWRITE_SYSTEM_PROMPT,
    REWRITE_USER_PROMPT,
    STARS_JSON_EXAMPLES_UK,
    STARS_JSON_SYSTEM_PROMPT,
    STARS_JSON_USER_PROMPT_BODY,
    STARS_SHOTS_UK,
)
from app.services.news_format import (
    build_news_blocks,
    build_urgent_news_lines,
    news_hashtag_for_category,
    sanitize_news_copy,
)
from app.utils.text import hashtagify, truncate

log = structlog.get_logger()

METADATA_MARKER_RE = re.compile(r"(?:^|\s)(?:image_url|imageUrl|source_image_url)\s*=\s*\S+", re.IGNORECASE)

# Lines the OpenAI path may emit; stripped in _sanitize_openai_post_text.
OPENAI_META_LINE_PATTERNS = (
    re.compile(r"^\s*у\s+матеріалі\s+", re.IGNORECASE),
    re.compile(r"^\s*беремо\s+тільки\s+факти", re.IGNORECASE),
    re.compile(r"короткий\s+опис\s+події", re.IGNORECASE),
    re.compile(r"інфопривід\s+у\s+заголовку", re.IGNORECASE),
    re.compile(r"є\s+короткий\s+опис", re.IGNORECASE),
    re.compile(r"деталі\s+уточнюються", re.IGNORECASE),
    re.compile(r"очікуємо\s+більше\s+інформації", re.IGNORECASE),
)

ENTITY_DISPLAY_ALIASES = {
    entry["name"]: next(
        (
            alias
            for alias in entry.get("aliases", [])
            if re.search(r"[А-Яа-яІіЇїЄєҐґ]", alias)
        ),
        entry["name"],
    )
    for entry in DEFAULT_TRACKED_ENTITIES
}


class RewriteService:
    def __init__(
        self,
        language: str = "uk",
        enable_openai: bool = False,
        api_key: str = "",
        model: str = "gpt-4o-mini",
        content_scope: str = "stars",
    ):
        self.language = language
        self.enable_openai = enable_openai and bool(api_key)
        self.api_key = api_key
        self.model = model
        self.content_scope = content_scope

    def _is_ukraine_news(self, item: NormalizedItem) -> bool:
        return self.content_scope == "ukraine_news"

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
        snippet = truncate(self._story_text(item.raw_snippet or item.raw_body), 1000)
        if self._is_ukraine_news(item):
            system_prompt = NEWS_REWRITE_SYSTEM_PROMPT
            user_prompt = (
                NEWS_REWRITE_USER_PROMPT.format(
                    category=item.category,
                    source=item.source_name,
                    title=item.title,
                    snippet=snippet,
                    url=item.url,
                )
                + "\n\nЕталонні приклади (структура й тон):\n"
                + NEWS_SHOTS_UK
            )
            temperature = 0.55
        else:
            if item.matched_entities:
                system_prompt = STARS_JSON_SYSTEM_PROMPT
                user_prompt = (
                    STARS_JSON_USER_PROMPT_BODY.format(
                        title=item.title,
                        snippet=snippet,
                        source=item.source_name,
                        entity_anchor=", ".join(item.matched_entities) or "українська зірка",
                        category=item.category,
                        has_image="так" if self._item_has_scrape_image_url(item) else "ні",
                    )
                    + "\n"
                    + STARS_JSON_EXAMPLES_UK
                    + "\n\nДодаткові еталони тону (не копіюй дослівно, лише ритм поста в Telegram):\n"
                    + STARS_SHOTS_UK
                )
            else:
                system_prompt = REWRITE_SYSTEM_PROMPT
                user_prompt = (
                    REWRITE_USER_PROMPT.format(
                        language=self.language,
                        category=item.category,
                        entity=", ".join(item.matched_entities) or "українська зірка",
                        source=item.source_name,
                        title=item.title,
                        snippet=snippet,
                    )
                    + "\n\nЕталонні приклади (структура й тон):\n"
                    + STARS_SHOTS_UK
                )
            temperature = 0.55 if item.matched_entities else 0.7
        response = client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        return self._coerce_result(payload, item)

    def _sanitize_openai_post_text(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if any(p.search(stripped) for p in OPENAI_META_LINE_PATTERNS):
                continue
            lines.append(line)
        return "\n\n".join(lines).strip()

    def _item_has_scrape_image_url(self, item: NormalizedItem) -> bool:
        raw_value = f"{item.raw_body or ''}\n{item.raw_snippet or ''}"
        marker = "image_url="
        if marker not in raw_value:
            return False
        candidate = raw_value.split(marker, 1)[1].split("\n", 1)[0].split()[0].strip()
        return candidate.startswith("http")

    def _is_stars_llm_json_payload(self, payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        entity = str(payload.get("entity") or "").strip()
        event = str(payload.get("event") or "").strip()
        text = str(payload.get("text") or "").strip()
        return bool(entity and event and text)

    def _normalize_llm_star_category(self, raw: str) -> str:
        allowed = {"relationships", "money", "concerts", "scandal", "lifestyle", "other", "social"}
        c = (raw or "other").strip().casefold()
        if c not in allowed:
            return "other"
        if c == "social":
            return "lifestyle"
        return c

    def _truncate_words(self, value: str, max_words: int = 10) -> str:
        words = value.split()
        if len(words) <= max_words:
            return value.strip()
        return " ".join(words[:max_words]).strip()

    def _split_star_llm_text_to_fact_lines(self, body: str, max_lines: int = 2) -> list[str]:
        parts = [p.strip() for p in body.split("\n") if p.strip()]
        if len(parts) >= 2:
            out = []
            for p in parts[:max_lines]:
                out.append(self._ensure_sentence(truncate(p, 115)))
            return out
        sentences = self._sentences(body)
        out: list[str] = []
        for s in sentences:
            t = self._ensure_sentence(truncate(s.strip(), 115))
            if t:
                out.append(t)
            if len(out) >= max_lines:
                break
        return out if out else [self._ensure_sentence(truncate(body.strip(), 200))]

    def _stars_hook_line(self, entity: str, category: str, event: str) -> str:
        cat = category.casefold().strip()
        if cat == "relationships":
            return f"💔 {entity}: {event}"
        if cat == "money":
            return f"💰 {entity}: {event}"
        if cat == "concerts":
            return f"🔥 {entity}: {event}"
        if cat == "scandal":
            return f"😱 Скандал навколо {entity}: {event}"
        if cat in {"lifestyle", "social"}:
            return f"😳 {entity}: {event}"
        return f"👀 {entity}: {event}"

    def _stars_icon(self, category: str, text: str) -> str:
        lowered = f"{category} {text}".casefold()
        if category == "scandal" or any(word in lowered for word in ("сканд", "конфлікт", "свар", "зрадниц", "хейт")):
            return "🫣"
        if category == "relationships" or any(
            word in lowered for word in ("роман", "розлуч", "одруж", "кохан", "чоловік", "дружин", "стосунк")
        ):
            return "💔"
        if category == "money" or any(word in lowered for word in ("гроші", "зароб", "мільйон", "гонорар", "будинок")):
            return "💸"
        if category == "concerts" or any(word in lowered for word in ("концерт", "гастрол", "квитк", "сцена")):
            return "🔥"
        if any(word in lowered for word in ("фото", "схуд", "фігур", "образ", "прес", "змінилась")):
            return "😳"
        return "👀"

    def _rewrite_result_from_stars_json(self, payload: dict[str, Any], item: NormalizedItem) -> RewriteResult | None:
        entity = self._clean_text(str(payload.get("entity") or ""))
        event_raw = self._clean_text(str(payload.get("event") or ""))
        body = self._sanitize_openai_post_text(str(payload.get("text") or "")).strip()
        if not entity or not event_raw or not body:
            return None
        cat = self._normalize_llm_star_category(str(payload.get("category") or "other"))
        event = self._truncate_words(event_raw, 10)
        pulse_raw = payload.get("pulse")
        pulse: str | None
        if pulse_raw is None:
            pulse = None
        else:
            s = self._clean_text(str(pulse_raw))
            if s.casefold() in {"null", "none"}:
                pulse = None
            else:
                pulse = s or None

        hook_line = self._stars_hook_line(entity, cat, event)
        fact_lines = self._split_star_llm_text_to_fact_lines(body)
        fact_block = self._star_fact_block(event, fact_lines)
        html_post = self._build_stars_html_post(
            item=item,
            entity=entity,
            event=event,
            fact_block=fact_block,
            context=pulse or self._star_context_for(item, entity, event),
            consequence=self._star_consequence_for(item, entity),
            category=cat,
        )

        image_query_out: str | None = None
        if not self._item_has_scrape_image_url(item):
            iq = payload.get("image_query")
            if iq is not None:
                q = self._clean_text(str(iq))
                if q and len(q) >= 3:
                    image_query_out = truncate(q, 120)

        return RewriteResult(
            hook=hook_line,
            text=html_post,
            short_title=truncate(event, 90),
            hashtags=["#зірки"],
            image_query=image_query_out,
        )

    def _coerce_result(self, payload: dict[str, Any], item: NormalizedItem) -> RewriteResult:
        if self._is_ukraine_news(item):
            return self._fallback_rewrite(item)

        if item.matched_entities and self._is_stars_llm_json_payload(payload):
            stars_result = self._rewrite_result_from_stars_json(payload, item)
            if stars_result:
                return stars_result

        hook = truncate(str(payload.get("hook") or item.title), 140)
        raw_text = str(payload.get("text") or "")
        text = truncate(self._sanitize_openai_post_text(raw_text), 520)
        hashtags = [str(tag) for tag in payload.get("hashtags", [])][:3]
        if not text:
            return self._fallback_rewrite(item)
        return RewriteResult(
            hook=hook,
            text=text,
            short_title=truncate(str(payload.get("short_title") or item.title), 90),
            hashtags=hashtags or self._default_hashtags(item),
            image_query=None,
        )

    def _fallback_rewrite(self, item: NormalizedItem) -> RewriteResult:
        post = self._build_final_post(item)
        hook = post.splitlines()[0].strip()
        return RewriteResult(
            hook=hook,
            text=post,
            short_title=truncate(item.title, 90),
            hashtags=self._default_hashtags(item),
        )

    def _build_final_post(self, item: NormalizedItem) -> str:
        if self._is_ukraine_news(item):
            if item.category == "emergency":
                return self._build_urgent_post(item)
            return self._build_news_post(item)
        if item.matched_entities:
            return self._build_stars_post(item)
        if item.category == "emergency":
            return self._build_urgent_post(item)
        return self._build_news_post(item)

    def _build_news_post(self, item: NormalizedItem) -> str:
        title = self._clean_headline(item.title)
        facts = self._fact_lines(item, max_lines=2, for_ukraine_news=self._is_ukraine_news(item))
        if self._is_ukraine_news(item):
            hashtag = news_hashtag_for_category(item.category)
            lines = build_news_blocks(item, title, facts, hashtag)
            post = self._finalize_lines(lines)
            return sanitize_news_copy(post)
        if len(facts) >= 2:
            fact_para = f"{facts[0]}\n{facts[1]}"
        elif facts:
            fact_para = facts[0]
        else:
            fact_para = title
        lines = [
            f"⚡️ {title}",
            fact_para,
            f"📊 {self._context_for(item)}",
            self._source_line(item),
            f"👉 Деталі:\n{item.url}",
            "#новини",
        ]
        return self._finalize_lines(lines)

    def _build_urgent_post(self, item: NormalizedItem) -> str:
        title = self._clean_headline(item.title)
        facts = self._fact_lines(item, max_lines=2, for_ukraine_news=self._is_ukraine_news(item))
        if self._is_ukraine_news(item):
            hashtag = news_hashtag_for_category(item.category)
            lines = build_urgent_news_lines(item, title, facts, hashtag)
            post = self._finalize_lines(lines)
            return sanitize_news_copy(post)
        f1 = facts[0] if facts else title
        f2 = facts[1] if len(facts) > 1 else f1
        fact_para = f"{f1}\n{f2}" if f1 != f2 else f1
        lines = [f"🚨 Терміново: {title}", fact_para, f"👉 Деталі:\n{item.url}", "#новини"]
        return self._finalize_lines(lines)

    def _build_stars_post(self, item: NormalizedItem) -> str:
        raw_entity = item.matched_entities[0]
        entity = self._display_entity_name(raw_entity, item)
        facts = self._fact_lines(item, max_lines=2, for_stars=True)
        event = self._star_event(item, entity)
        context = self._star_context_for(item, entity, event)

        hook = self._stars_hook_line(entity, item.category, event)
        fact_block = self._star_fact_block(event, facts)
        consequence = self._star_consequence_for(item, entity)
        return self._build_stars_html_post(
            item=item,
            entity=entity,
            event=event,
            fact_block=fact_block,
            context=context if not self._should_omit_star_pulse(hook, facts, context) else "",
            consequence=consequence,
            category=item.category,
        )

    def _build_stars_html_post(
        self,
        *,
        item: NormalizedItem,
        entity: str,
        event: str,
        fact_block: str,
        context: str,
        consequence: str,
        category: str,
    ) -> str:
        icon = self._stars_icon(category, f"{entity} {event} {fact_block}")
        headline = self._star_html_headline(entity, event, category)
        lines = [f"{icon}<b>{self._html(headline)}</b>"]
        body = self._star_compact_body(event, fact_block, context, consequence, category)
        if body:
            lines.append(self._html(body))
        source = self._html_source_link(item)
        if source:
            lines.append(source)
        lines.append('<b><a href="https://t.me/uastarsnews">UA Stars News</a></b>')
        return self._finalize_lines(lines)

    def _star_html_headline(self, entity: str, event: str, category: str) -> str:
        if category == "scandal":
            return f"Скандал навколо {entity}: {event}"
        if category == "relationships":
            return f"{entity}: {event}"
        if category == "money":
            return f"{entity}: {event}"
        if category == "concerts":
            return f"{entity}: {event}"
        return f"{entity}: {event}"

    def _star_compact_body(
        self,
        event: str,
        fact_block: str,
        context: str,
        consequence: str,
        category: str,
    ) -> str:
        for line in fact_block.splitlines():
            line = self._clean_text(line).strip()
            if not line or self._is_generic_star_line(line):
                continue
            if self._word_overlap_ratio(line, event) >= 0.55:
                continue
            return truncate(line, 165)
        if category == "concerts":
            concert_line = self._concert_compact_body(event)
            if concert_line:
                return concert_line
        for line in (context, consequence):
            line = self._clean_text(line).strip()
            if line and not self._is_generic_star_line(line) and self._word_overlap_ratio(line, event) < 0.5:
                return truncate(line, 150)
        return ""

    def _is_generic_star_line(self, line: str) -> bool:
        lowered = line.casefold()
        generic_bits = (
            "є сторінка події",
            "перед плануванням",
            "фанати дивляться",
            "фанам варто",
            "одна деталь швидко",
            "особиста деталь одразу",
            "нове фото стало",
            "публічна заява швидко",
            "публічна реакція стала",
            "цю деталь легко",
            "знову в центрі уваги",
            "образ знову виніс",
            "підписники шукають",
        )
        return any(bit in lowered for bit in generic_bits)

    def _concert_compact_body(self, event: str) -> str:
        parts = [part.strip() for part in event.split("|") if part.strip()]
        if len(parts) >= 2:
            return truncate(parts[-1], 150)
        return ""

    def _html_source_link(self, item: NormalizedItem) -> str | None:
        if not item.url:
            return None
        source = self._clean_text(item.source_name) or "джерело"
        return f'Дивитися в джерелі: <a href="{self._html_attr(item.url)}">{self._html(source)}</a>'

    def _html(self, value: str) -> str:
        return html.escape(value or "", quote=False)

    def _html_attr(self, value: str) -> str:
        return html.escape(value or "", quote=True)

    def _display_entity_name(self, entity: str, item: NormalizedItem) -> str:
        if self._is_stylized_stage_name(entity):
            return entity
        haystack = f"{item.title} {item.raw_snippet} {item.raw_body}"
        aliases = []
        for entry in DEFAULT_TRACKED_ENTITIES:
            if entry["name"] == entity:
                aliases = list(entry.get("aliases", []))
                break
        for alias in aliases:
            if alias and re.search(r"[А-Яа-яІіЇїЄєҐґ]", alias) and alias.casefold() in haystack.casefold():
                return alias
        return ENTITY_DISPLAY_ALIASES.get(entity, entity)

    def _is_stylized_stage_name(self, entity: str) -> bool:
        compact = re.sub(r"[\W_]+", "", entity)
        return bool(compact) and entity.upper() == entity and any("A" <= char <= "Z" for char in entity)

    def _star_fact_block(self, event: str, facts: list[str]) -> str:
        cleaned_event = self._clean_star_event_for_body(event)
        chosen: list[str] = []
        for fact in facts:
            if self._word_overlap_ratio(fact, cleaned_event) >= 0.6:
                continue
            chosen.append(fact)
            if len(chosen) >= 2:
                break
        if chosen:
            return "\n".join(chosen)
        return self._fallback_star_fact(cleaned_event)

    def _clean_star_event_for_body(self, event: str) -> str:
        event = re.sub(r"\s*\((?:фото|відео)\)\s*$", "", event.strip(), flags=re.IGNORECASE)
        event = event.strip(" .—-:|")
        return event or "нова деталь зʼявилася у шоу-бізнесі"

    def _fallback_star_fact(self, event: str) -> str:
        lowered = event.casefold()
        if any(word in lowered for word in ("схуд", "фігур", "образ", "лук", "вбран", "фото", "прес")):
            return "Нове фото стало головною деталлю історії."
        if any(word in lowered for word in ("одруж", "розлуч", "роман", "кохан", "стосунк", "чоловік", "дружин", "син", "донь")):
            return "Особиста деталь одразу потрапила в центр уваги."
        if any(word in lowered for word in ("концерт", "квитк", "тур", "зал", "сцена")):
            return "Фанати вже дивляться на дату, місто й квитки."
        if any(word in lowered for word in ("сканд", "конфіск", "свар", "конфлікт", "відреаг")):
            return "Публічна реакція стала головним нервом історії."
        if any(word in lowered for word in ("заяв", "зізнал", "розпов")):
            return "Публічна заява швидко стала інфоприводом."
        return "Одна деталь швидко винесла історію в стрічку."

    def _fact_lines(
        self, item: NormalizedItem, max_lines: int, *, for_stars: bool = False, for_ukraine_news: bool = False
    ) -> list[str]:
        title = self._clean_headline(item.title)
        body = self._body_without_repeated_title(item)
        if body == "Деталі — у матеріалі джерела.":
            if item.category == "concerts":
                return [
                    "Є сторінка події з датою, містом і квитками.",
                    "Перед плануванням варто перевірити дату, місто та наявність місць.",
                ][:max_lines]
            if item.matched_entities:
                return [] if for_stars else [self._title_fact_line(title)][:max_lines]
            if for_ukraine_news:
                return [self._ensure_sentence(truncate(title, 115))][:max_lines]
            return ["Є короткий опис події без додаткових деталей."][:max_lines]
        sentences = self._sentences(body)
        facts: list[str] = []
        for sentence in sentences:
            cleaned = self._strip_title_repetition(sentence, title).strip(" .—-:|\n\t")
            if not cleaned or cleaned.casefold() == title.casefold():
                continue
            facts.append(self._ensure_sentence(truncate(cleaned, 115)))
            if len(facts) >= max_lines:
                break
        if facts:
            return facts
        if for_stars:
            return []
        if for_ukraine_news:
            return [self._ensure_sentence(truncate(title, 115))][:max_lines]
        return ["Деталі поки короткі."]

    def _context_for(self, item: NormalizedItem) -> str:
        labels = {
            "politics": "Важливо для політичного контексту України.",
            "war": "Важливо для безпеки та ситуації на фронті.",
            "emergency": "Ситуація може оновлюватися.",
            "economy": "Це може вплинути на рішення бізнесу, ціни та щоденні витрати людей.",
            "world": "Має значення для міжнародного контексту.",
            "sports": "Українці стежать за результатом.",
            "tech": "Тема швидко набирає увагу онлайн.",
        }
        return labels.get(item.category, "Тема набирає увагу в українському інфопросторі.")

    def _source_line(self, item: NormalizedItem) -> str:
        source = self._clean_text(item.source_name)
        if not source:
            return "Джерело для перевірки: українські медіа, оригінальний лінк нижче у пості."
        return f"Джерело для перевірки: {truncate(source, 70)}, оригінальний лінк нижче у пості."

    def _star_event(self, item: NormalizedItem, entity: str) -> str:
        title = self._clean_headline(item.title)
        event = self._strip_leading_date(title)
        event = self._remove_entity_prefix(event, entity)
        event = event.strip(" .—-:|")
        if not event:
            fl = self._fact_lines(item, max_lines=1, for_stars=True)
            if fl:
                event = self._remove_entity_prefix(fl[0], entity).strip(" .—-:|")
        return truncate(event or "нова подія у шоу-бізнесі", 92)

    def _word_overlap_ratio(self, a: str, b: str) -> float:
        wa = set(re.findall(r"[\w''-]+", a.casefold()))
        wb = set(re.findall(r"[\w''-]+", b.casefold()))
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / len(wa | wb)

    def _should_omit_star_pulse(self, hook: str, facts: list[str], pulse: str) -> bool:
        """Skip 📊 when it mostly repeats the hook or the single fact line."""
        p = pulse.strip()
        if not p:
            return True
        hook_tail = hook.split(":", 1)[-1].strip() if ":" in hook else hook
        if self._word_overlap_ratio(p, hook_tail) >= 0.42:
            return True
        if facts and self._word_overlap_ratio(p, facts[0]) >= 0.38:
            return True
        return False

    def _star_context_for(self, item: NormalizedItem, _entity: str, _event: str) -> str:
        title_and_body = self._clean_text(f"{item.title} {item.raw_snippet} {item.raw_body}").casefold()
        labels = {
            "relationships": "Особисте життя знову в центрі уваги.",
            "money": "Гроші й дорогі рішення швидко чіпляють аудиторію.",
            "concerts": "Фанати дивляться на дату, місто й квитки.",
            "scandal": "Реакція вже розлітається соцмережами.",
            "social": "Історія пішла з соцмереж у новинні стрічки.",
            "lifestyle": "Образ і фото стали головним тригером обговорення.",
        }
        if any(word in title_and_body for word in ("схуд", "фігур", "образ", "лук", "вбран", "фото")):
            return "Фото й образ стали головним тригером обговорення."
        if any(word in title_and_body for word in ("одруж", "розлуч", "роман", "кохан", "стосунк", "чоловік", "дружин")):
            return "Особисте життя знову в центрі уваги."
        return labels.get(item.category, "Цю деталь легко підхоплюють у коментарях.")

    def _star_consequence_for(self, item: NormalizedItem, entity: str) -> str:
        title_and_body = self._clean_text(f"{item.title} {item.raw_snippet} {item.raw_body}").casefold()
        if item.category == "concerts":
            return "Фанам варто перевірити дату й квитки."
        if item.category == "scandal":
            return "Тепер увага — на реакції сторін."
        if item.category == "relationships":
            return "Підписники шукають нові деталі."
        if item.category == "money":
            return "Цифри можуть стати новим приводом для дискусії."
        if any(word in title_and_body for word in ("схуд", "фігур", "образ", "лук", "вбран", "фото")):
            return "Образ знову виніс зірку в обговорення."
        if entity:
            return f"{entity} знову в центрі уваги."
        return "Історія вже працює як привід для обговорення."

    def _strip_leading_date(self, text: str) -> str:
        return re.sub(r"^\d{1,2}\.\d{1,2}\.\d{4}\s*[-–—]\s*\d{1,2}:\d{2}\s*", "", text).strip()

    def _remove_entity_prefix(self, text: str, entity: str) -> str:
        aliases = [entity, *entity.split()]
        cleaned = text
        for alias in aliases:
            pattern = re.compile(rf"^{re.escape(alias)}(?:\s*[:—–-]\s*|\s+)", re.IGNORECASE)
            cleaned = pattern.sub("", cleaned).strip()
        return cleaned

    def _body_without_repeated_title(self, item: NormalizedItem) -> str:
        title = self._clean_text(item.title)
        for candidate in (item.raw_snippet, item.raw_body):
            body = self._story_text(candidate)
            if not body:
                continue
            body = self._strip_title_repetition(body, title)
            if body and body.casefold() != title.casefold():
                return truncate(body, 360)
        return "Деталі — у матеріалі джерела."

    def _strip_title_repetition(self, text: str, title: str) -> str:
        cleaned = text
        for _ in range(4):
            if title and cleaned.casefold().startswith(title.casefold()):
                cleaned = cleaned[len(title) :].lstrip(" .—-:|\n\t")
                continue
            break
        return cleaned

    def _sentences(self, text: str) -> list[str]:
        normalized = self._clean_text(text)
        parts = []
        current = []
        for char in normalized:
            current.append(char)
            if char in ".!?…":
                part = "".join(current).strip()
                if part:
                    parts.append(part)
                current = []
        tail = "".join(current).strip()
        if tail:
            parts.append(tail)
        return parts or ([normalized] if normalized else [])

    def _clean_headline(self, value: str) -> str:
        text = self._clean_text(value).strip(" .")
        return truncate(text, 105)

    def _ensure_sentence(self, value: str) -> str:
        value = value.strip()
        if value and value[-1] not in ".!?…":
            return f"{value}."
        return value

    def _title_fact_line(self, title: str) -> str:
        cleaned = title.strip(" .")
        if not cleaned:
            return "Деталі можна перевірити за посиланням нижче."
        return self._ensure_sentence(truncate(f"Інфопривід у заголовку: {cleaned}", 120))

    def _finalize_lines(self, lines: list[str]) -> str:
        cleaned = [line.strip() for line in lines if line and line.strip()]
        post = "\n\n".join(cleaned[:7])
        banned = (
            "як повідомляє джерело",
            "без зайвих висновків",
            "повідомляється",
            "за даними джерела",
            "основні деталі",
            "подаємо без висновків",
            "подаємо тільки перевірену рамку",
            "подаємо рамку",
            "джерело для перевірки",
            "тема набирає увагу",
            "важливо для політичного контексту україни",
        )
        for phrase in banned:
            post = post.replace(phrase, "")
        if len(post) <= 600:
            return post
        preserved = cleaned[-3:]
        body = cleaned[:-3]
        while body and len("\n\n".join([*body, *preserved])) > 600:
            body[-1] = truncate(body[-1], max(45, len(body[-1]) - 35))
            if len(body[-1]) <= 55:
                body.pop()
        return "\n\n".join([*body, *preserved])

    def _clean_text(self, value: str | None) -> str:
        return " ".join((value or "").split())

    def _story_text(self, value: str | None) -> str:
        without_markers = METADATA_MARKER_RE.sub(" ", value or "")
        return self._clean_text(without_markers)

    def _default_hashtags(self, item: NormalizedItem) -> list[str]:
        if self._is_ukraine_news(item):
            return [news_hashtag_for_category(item.category)]
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
