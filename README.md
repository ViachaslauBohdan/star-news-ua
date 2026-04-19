# UA Stars Money Bot

UA Stars Money Bot is a Telegram-first media engine for Ukrainian celebrities, singers, public figures, and entertainment news. It scans selected sources, filters for tracked stars, removes duplicate stories, rewrites relevant items into short Telegram posts, and publishes them in dry-run, admin-review, or auto-publish mode.

The product is designed around monetization from day one: category tagging, source performance, artist frequency, posting cadence, future engagement metrics, sponsored post support, affiliate ticket links, and ad-slot insertion hooks.

## What It Does

- Monitors entertainment/news websites by RSS or HTML scraping.
- Detects stories about a tracked Ukrainian entertainment figure list.
- Normalizes title, URL, source, date, snippet/body preview, matched people, and category.
- Blocks exact duplicates with canonical URLs and fingerprints.
- Blocks near-duplicates with RapidFuzz title similarity.
- Rewrites stories into Telegram-ready Russian posts by default.
- Uses OpenAI when enabled, with a safe template fallback when disabled.
- Publishes to Telegram with HTML formatting and an optional source button.
- Stores analytics for discovered, relevant, and published content.

## Project Structure

```text
ua-stars-money-bot/
  app/
    main.py
    config.py
    logging_config.py
    models.py
    db.py
    prompts.py
    constants.py
    sources/
    services/
    telegram/
    utils/
  data/
  tests/
  .env.example
  requirements.txt
  README.md
```

## Setup

Use Python 3.12.

```bash
cd ua-stars-money-bot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main init-db
```

Edit `.env` with your Telegram bot token and target chats.

## Environment Variables

- `TELEGRAM_BOT_TOKEN`: Bot token from BotFather.
- `TELEGRAM_CHANNEL_ID`: Public channel or chat ID for auto-publishing.
- `TELEGRAM_ADMIN_CHAT_ID`: Admin chat for review drafts.
- `OPENAI_API_KEY`: Optional key for AI rewriting.
- `APP_LANGUAGE`: `uk` by default. Posts should stay Ukrainian-only.
- `DRY_RUN`: When `true`, no real Telegram messages are sent.
- `AUTO_PUBLISH`: When `true`, posts go directly to `TELEGRAM_CHANNEL_ID`.
- `PREVIEW_MODE`: Logs drafts without publishing or review sending.
- `ENABLE_OPENAI`: Enables OpenAI rewriting if an API key is present.
- `SCAN_INTERVAL_MINUTES`: Default `15`.
- `RELEVANCE_THRESHOLD`: Default `60`.
- `FUZZY_DUP_THRESHOLD`: Default `88`.
- `AD_SLOT_EVERY_N_POSTS`: Reserved monetization knob for ad placement cadence.
- `MAX_PUBLISH_PER_RUN`: Maximum real posts per scan run. Default `2` to avoid publishing an old backlog all at once.
- `ENABLE_INSTAGRAM`: Enables Instagram ingestion from a compliant provider feed or local JSON exports.
- `INSTAGRAM_EXPORT_DIR`: Folder for JSON exports. Default `data/social/instagram`.
- `INSTAGRAM_FEED_URL`: Optional JSON endpoint from a provider/export pipeline.
- `INSTAGRAM_HANDLES_JSON`: JSON object mapping tracked entity names to Instagram handles.
- `DB_PATH`: Default `data/app.db`.
- `LOG_LEVEL`: Default `INFO`.

## Running Locally

Initialize the database and seed default sources/entities:

```bash
python -m app.main init-db
```

Run one scan:

```bash
python -m app.main scan-once
```

Run continuously:

```bash
python -m app.main run
```

Print an admin analytics summary:

```bash
python -m app.main summary
```

## Source Pipeline

Every source adapter exposes:

```python
fetch_items() -> list[RawItem]
```

The current adapters are:

- `TSN Glamur`
- `UNIAN Lite Stars`
- `Oboz Show`
- `Lux FM Stars`
- `Viva Stars`
- `Concert.ua Concerts`
- `Karabas Concerts`
- `Kontramarka Concerts`
- `TicketsBox Events`
- `ICTV Fakty Entertainment`
- `Novyny LIVE Showbiz`
- `RBC Ukraine Lite`
- `Clutch Showbiz`
- `Glavred Stars`
- `1plus1 Star Life`
- `1plus1 Show`

RSS support is implemented in `app/sources/rss_source.py`. Selector-based HTML support is implemented in `app/sources/html_source.py`. Ticket marketplaces use `app/sources/ticket_source.py`, which scans event-like links and marks matched items as `concerts`.

Site-specific files only define the base URL and selectors, so parser changes stay isolated.

Future social source stubs live in `app/sources/social_stubs.py` for Instagram, YouTube, and TikTok. They intentionally return no items until a compliant API/export integration is added.

Instagram can be enabled without login scraping by setting `ENABLE_INSTAGRAM=true` and providing either local JSON exports or a provider JSON endpoint. Example export:

```json
[
  {
    "username": "jamalajaaa",
    "caption": "Новий закулісний момент зі зйомок.",
    "shortcode": "ABC123",
    "timestamp": "2026-04-19T13:00:00+00:00"
  }
]
```

Example handle mapping:

```env
INSTAGRAM_HANDLES_JSON={"Jamala":"jamalajaaa","Tina Karol":"tina_karol"}
```

If one source fails, it logs a warning and the rest of the pipeline continues.

Sources include scoring fields:

- `priority`: scan order and monetization importance
- `credibility_score`: editorial trust level
- `entertainment_bias_score`: how focused the source is on showbiz content

## Relevance And Categories

The relevance engine checks the title, snippet, and body against active tracked entities and aliases. It assigns:

- matched celebrities
- main celebrity
- category
- relevance score from 0 to 100

Categories include:

- `scandal`
- `relationships`
- `money`
- `concerts`
- `lifestyle`
- `interviews`
- `social`
- `releases`
- `charity`
- `tv`
- `other`

Only items above `RELEVANCE_THRESHOLD` are eligible for publishing.

Each discovered item also stores `primary_entity`, `relevance_score`, `relevance_explanation`, `is_primary_story`, and `duplicate_group_id` for review, analytics, and future dashboard workflows.

## Tracked Artists

The default tracked list includes Jerry Heil, alyona alyona, DOROFEEVA, Tina Karol, Anna Trincher, KOLA, FIЇNKA, Olya Polyakova, Zlata Ognevich, MAMARIKA, YAKTAK, Artem Pivovarov, MÉLOVIN, SKOFKA, Kalush Orchestra, Okean Elzy, Klavdia Petrivna, MONATIK, Max Barskih, NK, Ivan NAVI, Wellboy, Parfeniuk, SadSvit, DOVI, Iryna Bilyk, Verka Serduchka, Sofia Rotaru, The Hardkiss, Antytila, and KAZKA.

Aliases cover Ukrainian, Russian, and Latin transliteration variants where practical.

## Duplicate Detection

There are two levels:

1. Exact duplicate detection by canonical URL and stable fingerprint.
2. Near-duplicate detection by normalized title similarity with RapidFuzz.

The fingerprint is derived from source, normalized title, and canonical URL. The fuzzy threshold is controlled by `FUZZY_DUP_THRESHOLD`.

## Telegram Publishing

The publisher supports:

- dry-run mode
- preview mode
- admin review mode
- auto-publish mode
- ad-slot insertion after every configured number of organic posts
- HTML-safe Telegram formatting
- source attribution
- inline "Читати джерело" button
- message length guardrails

Default Telegram template:

```text
🔥 {hook}

{text body}

Джерело: {source}
Читати: {url}

#artist #category
```

When `AUTO_PUBLISH=false`, drafts are sent to `TELEGRAM_ADMIN_CHAT_ID` if configured. When `AUTO_PUBLISH=true`, posts go to `TELEGRAM_CHANNEL_ID`.

## AI Rewriting

Two modes are supported:

- OpenAI mode with `ENABLE_OPENAI=true` and `OPENAI_API_KEY`.
- Fallback template rewrite with no external AI dependency.

Editorial rules:

- preserve facts
- do not fabricate claims or quotes
- label uncertainty softly
- avoid defamatory wording
- attribute the source
- keep the tone punchy but safe

## Adding A New Source

For a selector-based page, add a file under `app/sources/`:

```python
from app.sources.base import SourceConfig
from app.sources.html_source import HTMLSource

def make_source(timeout: int, user_agent: str) -> HTMLSource:
    return HTMLSource(
        SourceConfig(
            name="New Source",
            base_url="https://example.com/stars",
            selectors={
                "article": "article, .news-card",
                "title": "a, h2, h3",
                "link": "a",
                "snippet": "p, .excerpt",
            },
        ),
        timeout=timeout,
        user_agent=user_agent,
    )
```

Then insert it into the `sources` table and add the factory mapping in `SourceRunner._build_sources()`.

## Adding A Tracked Artist

Use SQLite or add to `DEFAULT_TRACKED_ENTITIES` in `app/constants.py`.

Database fields:

- `name`
- `entity_type`
- `aliases_json`
- `is_active`

Example alias list:

```json
["Tina Karol", "Тіна Кароль", "Тина Кароль"]
```

## Running On A VPS

Install Python 3.12, clone or copy the project, configure `.env`, then run it under systemd.

Example service:

```ini
[Unit]
Description=UA Stars Money Bot
After=network.target

[Service]
WorkingDirectory=/opt/ua-stars-money-bot
ExecStart=/opt/ua-stars-money-bot/.venv/bin/python -m app.main run
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

## Analytics

`python -m app.main summary` answers:

- total discovered
- total relevant
- total published
- top 10 celebrities by published mention count
- top categories
- top sources
- posts per day
- most used posting hours

The schema is ready for future Telegram engagement metrics:

- views
- forwards
- reactions
- sponsored post type
- ad slots sold
- affiliate clicks

## Monetization Roadmap

Near-term:

- grow a focused Telegram channel around Ukrainian star news
- measure which artists and categories generate the most publishable content
- insert direct ad slots after every N posts
- sell sponsored placements

Next:

- add affiliate ticket links for concerts and tours
- extract article images and create richer Telegram posts
- redirect selected stories to SEO pages
- track Telegram views, forwards, and reactions
- add sponsor inventory and simple CRM tables
- support Ukrainian and Russian post variants
- add an admin dashboard for approvals and performance

## Tests

```bash
pytest
```

Current tests cover relevance matching, duplicate detection, and Telegram formatting.
