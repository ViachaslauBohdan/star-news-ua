"""Ukrainian news Telegram posts: суть + реакція + наслідки (без пересказу й заглушок)."""

from __future__ import annotations

import hashlib
import html
import re

from app.models import NormalizedItem
from app.utils.text import truncate

# Single hashtag per post (Ukrainian)
NEWS_HASHTAG_BY_POOL: dict[str, str] = {
    "war": "#війна",
    "politics": "#політика",
    "world": "#світ",
    "economy": "#економіка",
    "security": "#безпека",
    "infrastructure": "#новини",
    "general": "#новини",
}

_CATEGORY_EMOJI_KEY: dict[str, str] = {
    "war": "war",
    "politics": "politics",
    "world": "world",
    "economy": "economy",
    "emergency": "security",
    "tech": "infrastructure",
}

_BANNED_SUBSTRINGS: tuple[str, ...] = (
    "повідомляється",
    "основні деталі",
    "подаємо тільки перевірену рамку",
    "подаємо без висновків",
    "подаємо рамку",
    "джерело для перевірки",
    "важливо для політичного контексту україни",
    "тема набирає увагу",
    "як повідомляє джерело",
    "за даними джерела",
    "без зайвих висновків",
    "подаємо без висновків",
    "є короткий опис",
    "деталі уточнюються",
    "очікуємо більше інформації",
    "деталі поки короткі",
    "це може вплинути",
    "ситуація може змінитися",
    "ситуація може оновлюватися",
    "інфопривід у заголовку",
    "йдеться про",
)

_NUMBER_RE = re.compile(r"\d[\d\s.,]*[%€$₴]?|\d+\s*(?:млн|млрд|тис|км|км²)")
_NUMBER_WITH_UNIT_RE = re.compile(
    r"\d[\d\s.,]*(?:\s*(?:млрд|млн|тис|мільярд(?:а|ів)?|мільйон(?:а|ів)?|євро|долар(?:а|ів)?|грн|₴|€|\$|мвт|гвт|км|%))*",
    re.IGNORECASE,
)

_METADATA_IN_SNIPPET_RE = re.compile(
    r"(?:^|\s)(?:image_url|imageUrl|source_image_url)\s*=\s*\S+",
    re.IGNORECASE,
)


def _pool_key_for_category(category: str) -> str:
    return _CATEGORY_EMOJI_KEY.get(category, "general")


def _rotation_seed(*parts: str) -> str:
    return "|".join(parts)


def _stable_index(seed: str, modulo: int) -> int:
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % modulo if modulo else 0


TOPNEWS_FOOTER = '<b><a href="https://t.me/topnewsuaUKR">TOPNEWS UA</a></b>'


def news_hashtag_for_category(category: str) -> str:
    key = _pool_key_for_category(category)
    return NEWS_HASHTAG_BY_POOL[key]


def sanitize_news_copy(text: str) -> str:
    """Remove banned vague / meta-reporting phrases (defense in depth)."""
    out = text
    lowered = out.casefold()
    for phrase in _BANNED_SUBSTRINGS:
        if phrase in lowered:
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            out = pattern.sub("", out)
            lowered = out.casefold()
    blocks = [b.strip() for b in out.split("\n\n")]
    blocks = [" ".join(b.split()) for b in blocks if b]
    return "\n\n".join(blocks)


def _strip_leading_title_repeat(text: str, title: str) -> str:
    cleaned = text
    t = title.strip()
    if not t:
        return cleaned
    for _ in range(24):
        if cleaned.casefold().startswith(t.casefold()):
            cleaned = cleaned[len(t) :].lstrip(" .—-:|\n\t")
            continue
        break
    return cleaned.strip()


def _norm_for_repeat_check(text: str) -> str:
    cleaned = re.sub(r"[^\wа-яіїєґА-ЯІЇЄҐ]+", " ", text or "", flags=re.UNICODE)
    return " ".join(cleaned.casefold().split())


def _is_repeat_of_title(text: str, title: str) -> bool:
    body = _norm_for_repeat_check(text)
    head = _norm_for_repeat_check(title)
    if not body or not head:
        return False
    return body == head or body in head or head in body


def _norm_number(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").casefold().replace(".", ","))


def _numbers_in(text: str) -> set[str]:
    return {
        _norm_number(match.group(0))
        for match in _NUMBER_WITH_UNIT_RE.finditer(text or "")
        if match.group(0).strip()
    }


def _remove_repeated_number_fragments(detail: str, title: str) -> str:
    title_numbers = _numbers_in(title)
    if not detail or not title_numbers:
        return detail

    parts = re.split(r"(\s*,\s+|\s+та\s+|\s+і\s+)", detail)
    cleaned: list[str] = []
    index = 0
    while index < len(parts):
        separator = parts[index - 1] if index > 0 else ""
        part = parts[index]
        if _numbers_in(part) & title_numbers:
            if cleaned and separator.strip() in {",", "та", "і"}:
                cleaned.pop()
            index += 2
            continue
        if separator and cleaned:
            cleaned.append(separator)
        cleaned.append(part)
        index += 2

    out = "".join(cleaned)
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r",\s*,+", ",", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip(" ,;")


def _clean_snippet_for_pair(snippet: str) -> str:
    without_meta = _METADATA_IN_SNIPPET_RE.sub(" ", snippet or "")
    return " ".join(without_meta.split())


def _is_weak_detail_line(text: str) -> bool:
    normalized = _norm_for_repeat_check(text)
    if not normalized:
        return True
    weak = {
        "джерела",
        "джерело",
        "змі",
        "медіа",
        "за даними джерела",
        "як повідомляє джерело",
        "деталі у джерелі",
        "подія вже змінює порядок денний",
    }
    if normalized in {_norm_for_repeat_check(value) for value in weak}:
        return True
    return any(_norm_for_repeat_check(phrase) in normalized for phrase in _BANNED_SUBSTRINGS)


def _sentences_from_text(text: str) -> list[str]:
    normalized = _clean_snippet_for_pair(text)
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?…])\s+", normalized)
    return [part.strip(" \n\t-—|") for part in parts if part.strip(" \n\t-—|")]


def _supporting_detail_line(title: str, facts: list[str], *raw_texts: str) -> str:
    """Second Telegram line: a real supporting detail/dek, not a generated filler."""
    candidates: list[str] = []
    for raw in raw_texts:
        cleaned = _strip_leading_title_repeat(_clean_snippet_for_pair(raw), title)
        candidates.extend(_sentences_from_text(cleaned))
    candidates.extend(fact for fact in facts if not _looks_pretruncated(fact))

    for candidate in candidates:
        if _looks_pretruncated(candidate):
            continue
        body = _remove_repeated_number_fragments(candidate, title)
        body = _short_line(body, 190).strip()
        if _is_weak_detail_line(body) or _is_repeat_of_title(body, title):
            continue
        if body and body[-1] not in ".!?…":
            body += "."
        return body
    return ""


def _fact_line_when_body_repeats_headline(title: str) -> str:
    """Один рядок «що сталося» без дослівного повтору заголовка."""
    t = " ".join(title.split()).strip(" .")
    lowered = t.casefold()
    if "зеленськ" in lowered and any(word in lowered for word in ("поговор", "обговор", "зустрів")):
        return "Президент веде координацію з партнерами."
    if any(word in lowered for word in ("скликає", "скликав", "рада", "нацбезпеки")):
        return "Уряд реагує на кризу через термінову нараду."
    if any(word in lowered for word in ("захопили", "перехопили")) and "судн" in lowered:
        return "Спробу проходу судна зупинили силою."
    if any(word in lowered for word in ("знешкодили", "ліквідували")):
        return "Сили оборони відзвітували про нові втрати ворога."
    if "мвф" in lowered or "пдв" in lowered or "фоп" in lowered:
        return "Фінансові умови для бізнесу знову переглядають."
    if any(word in lowered for word in ("ціни", "курс", "податк", "ринок")):
        return "Грошові правила для людей можуть змінитися."
    if any(word in lowered for word in ("вибор", "парламент")):
        return "Політичний баланс може змінитися після голосування."
    if any(word in lowered for word in ("відмов", "переговор")):
        return "Сторона виходить із переговорного треку."
    for sep in (" — ", " – ", " - ", ": "):
        if sep in t:
            tail = t.split(sep, 1)[1].strip(" .")
            if tail and tail.casefold() != t.casefold():
                out = tail[0].upper() + tail[1:] if len(tail) > 1 else tail.upper()
                if out[-1] not in ".!?…":
                    out += "."
                return truncate(out, 115)
    return ""


def _pair_facts(facts: list[str], title: str, snippet: str) -> tuple[str, str]:
    if len(facts) >= 2:
        return facts[0], facts[1]
    f1 = facts[0] if facts else truncate(title, 115)
    raw = _clean_snippet_for_pair(snippet)
    raw = _strip_leading_title_repeat(raw, title)
    if raw and raw.casefold() not in f1.casefold() and f1.casefold() not in raw.casefold():
        return f1, truncate(raw, 115)
    tnorm = title.casefold().strip(" .")
    fnorm = f1.casefold().strip(" .")
    if fnorm == tnorm or f1.casefold().count(tnorm) >= 2:
        f1 = _fact_line_when_body_repeats_headline(title)
    return f1, f1


def _short_line(text: str, max_chars: int = 82) -> str:
    return _complete_short_sentence(" ".join((text or "").split()), max_chars)


def _complete_short_sentence(text: str, max_chars: int) -> str:
    cleaned = " ".join((text or "").split()).strip(" .,…")
    if len(cleaned) <= max_chars:
        return cleaned
    limit = max(24, max_chars)
    head = cleaned[:limit].rstrip(" ,;:—-")
    cut_at = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if cut_at >= 36:
        return _trim_dangling_tail(head[:cut_at + 1])
    for sep in (", ", " — ", " – ", ": "):
        cut_at = head.rfind(sep)
        if cut_at >= 42:
            return _trim_dangling_tail(head[:cut_at])
    space_at = head.rfind(" ")
    if space_at >= 42:
        return _trim_dangling_tail(head[:space_at])
    return ""


def _html(value: str) -> str:
    return html.escape(value or "", quote=False)


def _html_attr(value: str) -> str:
    return html.escape(value or "", quote=True)


def _headline_candidate(text: str, max_chars: int = 86) -> str:
    cleaned = " ".join((text or "").split()).strip(" .,…")
    if len(cleaned) <= max_chars:
        return cleaned
    for sep in (": ", " — ", " – ", " - "):
        if sep in cleaned:
            first, rest = cleaned.split(sep, 1)
            if 28 <= len(first) <= max_chars:
                return first.strip(" .,…")
            combined_words: list[str] = []
            for word in rest.split():
                probe = (first + sep + " ".join([*combined_words, word])).strip()
                if len(probe) > max_chars:
                    break
                combined_words.append(word)
            if combined_words:
                return _trim_dangling_tail(first + sep + " ".join(combined_words))
    return _complete_short_sentence(cleaned, max_chars)


def _looks_pretruncated(text: str) -> bool:
    stripped = (text or "").strip()
    if "..." in stripped or "…" in stripped:
        return True
    words = stripped.split()
    return bool(words and len(words[-1]) <= 3 and stripped[-1:] not in ".!?:;)")


_DANGLING_TAIL_RE = re.compile(
    r"\s+(?:щодо|стосовно|через|після|перед|для|про|при|без|за|на|у|в|до|від|із|з|та|і|що|того|який|яка|яке|які)(?:\s+\w{1,12}){0,2}$",
    re.IGNORECASE,
)


def _trim_dangling_tail(text: str) -> str:
    out = (text or "").strip(" .,…")
    for _ in range(3):
        trimmed = _DANGLING_TAIL_RE.sub("", out).strip(" .,…")
        if trimmed == out or len(trimmed) < 28:
            break
        out = trimmed
    return out


def _reaction_headline(title: str) -> str:
    cleaned = re.sub(r"^\s*(змі|джерела|медіа)\s*:\s*", "", title, flags=re.IGNORECASE)
    lowered = cleaned.casefold()
    if "зеленськ" in lowered and any(word in lowered for word in ("поговор", "обговор")):
        return "Зеленський посилює переговори через партнерів"
    if any(word in lowered for word in ("захопили", "перехопили")) and "судн" in lowered:
        return "Судно перехопили: напруга різко зростає"
    if "мвф" in lowered and ("пдв" in lowered or "фоп" in lowered):
        return "МВФ відступив у питанні ПДВ для ФОПів"
    if "долар" in lowered or "курс" in lowered:
        return "Курс знову тисне на ринок"
    if "знешкодили" in lowered and "окупант" in lowered:
        return "Втрати РФ знову пішли вгору"
    return _headline_candidate(cleaned.strip(" ."), 86)


def _headline_prefix(category: str, title: str) -> str:
    lowered = f"{category} {title}".casefold()
    urgent_tokens = (
        "терміново",
        "атака",
        "атакували",
        "вибух",
        "дтп",
        "загин",
        "мобілізац",
        "відмов",
        "захоп",
        "перехоп",
        "зупини",
    )
    if category in {"emergency", "war", "politics", "world"} or any(token in lowered for token in urgent_tokens):
        return "❗️"
    if category in {"economy", "tech"}:
        return ""
    return ""


def _why_line(category: str, fingerprint: str) -> str:
    """Рядок після 💬 — напруга / важливість, без абстрактного «це може вплинути»."""
    key = _pool_key_for_category(category)
    variants = {
        "war": [
            "Напрямок стає гарячим для обох сторін",
            "Удари змінюють хід операції на землі",
            "Лінія фронту відчуває тиск без паузи",
        ],
        "politics": [
            "Це сигнал активізації дипломатії",
            "Союзники дивляться на чіткість домовленостей",
            "Діалог підтягує безпекові теми",
        ],
        "world": [
            "Напруга між сторонами різко зросла",
            "Морська блокада тягне за собою ризики",
            "Ескалація торкається торгових маршрутів",
        ],
        "economy": [
            "Податки й ФОПи відчують зміну режиму",
            "МВФ тримає руку на важелі ПДВ",
            "Бюджетні правила зміщуються в бік жорсткіших умов",
        ],
        "security": [
            "Людям важливо знати периметр небезпеки",
            "Тривога прив’язана до конкретної зони",
            "Служби відкривають вікно для уточнень",
        ],
        "infrastructure": [
            "Міста живуть від стабільних мереж",
            "Комунальні служби тримають дефіцит часу",
            "Постачання комплектуючих стає вузьким місцем",
        ],
        "general": [
            "Подія одразу заходить у стрічку новин",
            "Суспільна увага зміщується на факт",
            "Тема потребує короткого пояснення «нащо це»",
        ],
    }[key]
    return variants[_stable_index(_rotation_seed("why", category, fingerprint), len(variants))]


def _consequence_line(category: str, fingerprint: str) -> str:
    """Рядок після 👉 — наслідок / що змінюється, конкретно."""
    key = _pool_key_for_category(category)
    variants = {
        "war": [
            "Далі у зведенні з’являться уточнення",
            "Військові мають підтвердити масштаб",
            "Район триматимуть під посиленим контролем",
        ],
        "politics": [
            "Можливі нові домовленості з партнерами",
            "Наступні заяви покажуть план кроків",
            "Уряд має оформити позицію публічно",
        ],
        "world": [
            "Можливий новий виток конфлікту",
            "Реакція інших флотів стане видно за дні",
            "Санкції й обмін ударами лишаються на столі",
        ],
        "economy": [
            "Курс і платежі стежитимуть за рішенням",
            "Бізнес перерахує касові витрати",
            "Ціни на послуги підуть у перевірку ринку",
        ],
        "security": [
            "Графіки оновлять після обходу місця",
            "Рух обмежать до завершення робіт",
            "Офіційний канал дасть наступні цифри",
        ],
        "infrastructure": [
            "Дати відновлення озвучать після обстеження",
            "Ліміти на енергію продовжать діяти добу",
            "Нові графіки винесуть у застосунок",
        ],
        "general": [
            "Наступний рух сторін стане видно публічно",
            "Рішення суду або влади закриє питання",
            "Обговорення тримається на одному доказі",
        ],
    }[key]
    return variants[_stable_index(_rotation_seed("after", category, fingerprint), len(variants))]


def _detail_body(fact: str, title: str) -> str:
    body = _short_line(fact, 190).strip()
    if _is_weak_detail_line(body):
        body = ""
    if _is_repeat_of_title(body, title):
        body = ""
    if not body:
        body = _fact_line_when_body_repeats_headline(title)
    if _is_repeat_of_title(body, title):
        body = ""
    if body and body[-1] not in ".!?…":
        body += "."
    return body


def _source_link(item: NormalizedItem) -> str | None:
    if not item.url:
        return None
    source = " ".join((item.source_name or "").split()).strip() or "джерело"
    return f'Дивитися в джерелі: <a href="{_html_attr(item.url)}">{_html(source)}</a>'


def build_news_blocks(item: NormalizedItem, title: str, facts: list[str], hashtag: str) -> list[str]:
    """Telegram HTML news format for TOPNEWS UA."""
    f1, f2 = _pair_facts(facts, title, item.raw_snippet or item.raw_body or "")
    headline = _reaction_headline(title)
    prefix = _headline_prefix(item.category, title)
    lead = f"{prefix}<b>{_html(headline)}</b>" if prefix else f"<b>{_html(headline)}</b>"
    body = _supporting_detail_line(title, [f1, f2, *facts], item.raw_snippet, item.raw_body)
    lines = [lead]
    if body:
        lines.append(_html(body))
    source = _source_link(item)
    if source:
        lines.append(source)
    lines.append(TOPNEWS_FOOTER)
    return lines


def build_urgent_news_lines(item: NormalizedItem, title: str, facts: list[str], hashtag: str) -> list[str]:
    f1 = facts[0] if facts else title
    headline = _reaction_headline(title)
    lines = [f"❗️<b>{_html(headline)}</b>"]
    body = _supporting_detail_line(title, [*facts, f1], item.raw_snippet, item.raw_body)
    if body:
        lines.append(_html(body))
    source = _source_link(item)
    if source:
        lines.append(source)
    lines.append(TOPNEWS_FOOTER)
    return lines
