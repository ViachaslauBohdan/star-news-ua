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


def _clean_snippet_for_pair(snippet: str) -> str:
    without_meta = _METADATA_IN_SNIPPET_RE.sub(" ", snippet or "")
    return " ".join(without_meta.split())


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
    return "Подія вже змінює порядок денний."


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
    return truncate(" ".join((text or "").split()), max_chars)


def _html(value: str) -> str:
    return html.escape(value or "", quote=False)


def _html_attr(value: str) -> str:
    return html.escape(value or "", quote=True)


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
    return _short_line(cleaned.strip(" ."), 86)


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
    if not body:
        body = _fact_line_when_body_repeats_headline(title)
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
    f1, _ = _pair_facts(facts, title, item.raw_snippet or item.raw_body or "")
    headline = _reaction_headline(title)
    prefix = _headline_prefix(item.category, title)
    lead = f"{prefix}<b>{_html(headline)}</b>" if prefix else f"<b>{_html(headline)}</b>"
    body = _detail_body(f1, title)
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
    body = _detail_body(f1, title)
    if body:
        lines.append(_html(body))
    source = _source_link(item)
    if source:
        lines.append(source)
    lines.append(TOPNEWS_FOOTER)
    return lines
