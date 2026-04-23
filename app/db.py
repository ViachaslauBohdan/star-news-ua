from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from app.constants import DEFAULT_SOURCES, DEFAULT_TRACKED_ENTITIES
from app.models import ItemStatus, NormalizedItem, TrackedEntity

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Json
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None
    Json = None


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path | str, database_url: str = ""):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.database_url = database_url.strip()
        self.is_postgres = bool(self.database_url)
        if self.is_postgres and psycopg is None:
            raise RuntimeError("DATABASE_URL is set but psycopg is not installed")

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self.is_postgres:
            conn = psycopg.connect(self.database_url, row_factory=dict_row)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return

        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def migrate(self) -> None:
        if self.is_postgres:
            self._migrate_postgres()
            return
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    base_url TEXT NOT NULL,
                    type TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 50,
                    credibility_score INTEGER NOT NULL DEFAULT 70,
                    entertainment_bias_score INTEGER NOT NULL DEFAULT 70,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tracked_entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    entity_type TEXT NOT NULL DEFAULT 'person',
                    aliases_json TEXT NOT NULL DEFAULT '[]',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS discovered_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    published_at TEXT,
                    raw_snippet TEXT,
                    raw_body TEXT,
                    matched_entities_json TEXT NOT NULL DEFAULT '[]',
                    category TEXT NOT NULL DEFAULT 'other',
                    fingerprint TEXT NOT NULL UNIQUE,
                    similarity_key TEXT NOT NULL,
                    primary_entity TEXT,
                    relevance_score INTEGER NOT NULL DEFAULT 0,
                    relevance_explanation TEXT,
                    is_primary_story INTEGER NOT NULL DEFAULT 1,
                    duplicate_group_id INTEGER,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (source_id) REFERENCES sources(id)
                );

                CREATE INDEX IF NOT EXISTS idx_discovered_status ON discovered_items(status);
                CREATE INDEX IF NOT EXISTS idx_discovered_similarity ON discovered_items(similarity_key);
                CREATE INDEX IF NOT EXISTS idx_discovered_canonical ON discovered_items(canonical_url);

                CREATE TABLE IF NOT EXISTS published_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discovered_item_id INTEGER UNIQUE,
                    telegram_message_id INTEGER,
                    telegram_chat_id TEXT,
                    published_text TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    category TEXT,
                    post_type TEXT NOT NULL DEFAULT 'organic',
                    artist_main TEXT,
                    source_name TEXT,
                    views INTEGER,
                    forwards INTEGER,
                    reactions INTEGER,
                    ad_slots_sold INTEGER DEFAULT 0,
                    affiliate_clicks INTEGER DEFAULT 0,
                    FOREIGN KEY (discovered_item_id) REFERENCES discovered_items(id)
                );

                CREATE TABLE IF NOT EXISTS system_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    scanned_sources INTEGER NOT NULL DEFAULT 0,
                    discovered_count INTEGER NOT NULL DEFAULT 0,
                    relevant_count INTEGER NOT NULL DEFAULT 0,
                    published_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    notes TEXT
                );
                """
            )
            self._ensure_column(conn, "published_posts", "post_type", "TEXT NOT NULL DEFAULT 'organic'")
            self._ensure_column(conn, "sources", "priority", "INTEGER NOT NULL DEFAULT 50")
            self._ensure_column(conn, "sources", "credibility_score", "INTEGER NOT NULL DEFAULT 70")
            self._ensure_column(conn, "sources", "entertainment_bias_score", "INTEGER NOT NULL DEFAULT 70")
            self._ensure_column(conn, "discovered_items", "primary_entity", "TEXT")
            self._ensure_column(conn, "discovered_items", "relevance_score", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "discovered_items", "relevance_explanation", "TEXT")
            self._ensure_column(conn, "discovered_items", "is_primary_story", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "discovered_items", "duplicate_group_id", "INTEGER")

    def _migrate_postgres(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    base_url TEXT NOT NULL,
                    type TEXT NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    priority INTEGER NOT NULL DEFAULT 50,
                    credibility_score INTEGER NOT NULL DEFAULT 70,
                    entertainment_bias_score INTEGER NOT NULL DEFAULT 70,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tracked_entities (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    entity_type TEXT NOT NULL DEFAULT 'person',
                    aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discovered_items (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    source_id BIGINT REFERENCES sources(id),
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    published_at TEXT,
                    raw_snippet TEXT,
                    raw_body TEXT,
                    matched_entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    category TEXT NOT NULL DEFAULT 'other',
                    fingerprint TEXT NOT NULL UNIQUE,
                    similarity_key TEXT NOT NULL,
                    primary_entity TEXT,
                    relevance_score INTEGER NOT NULL DEFAULT 0,
                    relevance_explanation TEXT,
                    is_primary_story BOOLEAN NOT NULL DEFAULT TRUE,
                    duplicate_group_id BIGINT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_status ON discovered_items(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_similarity ON discovered_items(similarity_key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_canonical ON discovered_items(canonical_url)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS published_posts (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    discovered_item_id BIGINT UNIQUE REFERENCES discovered_items(id),
                    telegram_message_id BIGINT,
                    telegram_chat_id TEXT,
                    published_text TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    category TEXT,
                    post_type TEXT NOT NULL DEFAULT 'organic',
                    artist_main TEXT,
                    source_name TEXT,
                    views INTEGER,
                    forwards INTEGER,
                    reactions INTEGER,
                    ad_slots_sold INTEGER DEFAULT 0,
                    affiliate_clicks INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_runs (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    scanned_sources INTEGER NOT NULL DEFAULT 0,
                    discovered_count INTEGER NOT NULL DEFAULT 0,
                    relevant_count INTEGER NOT NULL DEFAULT 0,
                    published_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    notes TEXT
                )
                """
            )

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def seed_defaults(self, app_profile: str = "stars", *, enable_telethon_sources: bool = False) -> None:
        profile = app_profile.strip().lower()
        with self.connect() as conn:
            for source in DEFAULT_SOURCES:
                default_enabled = source.get("enabled", 1)
                if profile == "news":
                    if source.get("group") == "news":
                        default_enabled = 1
                    elif source.get("group") == "news_telethon":
                        default_enabled = 1 if enable_telethon_sources else 0
                    else:
                        default_enabled = 0
                if self.is_postgres:
                    conn.execute(
                        """
                        INSERT INTO sources (
                            name, base_url, type, enabled, priority, credibility_score,
                            entertainment_bias_score, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (name) DO UPDATE
                        SET base_url = EXCLUDED.base_url,
                            type = EXCLUDED.type,
                            enabled = EXCLUDED.enabled,
                            priority = EXCLUDED.priority,
                            credibility_score = EXCLUDED.credibility_score,
                            entertainment_bias_score = EXCLUDED.entertainment_bias_score
                        """,
                        (
                            source["name"],
                            source["base_url"],
                            source["type"],
                            bool(default_enabled),
                            source.get("priority", 50),
                            source.get("credibility_score", 70),
                            source.get("entertainment_bias_score", 70),
                            utc_now_iso(),
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO sources (
                            name, base_url, type, enabled, priority, credibility_score,
                            entertainment_bias_score, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            source["name"],
                            source["base_url"],
                            source["type"],
                            default_enabled,
                            source.get("priority", 50),
                            source.get("credibility_score", 70),
                            source.get("entertainment_bias_score", 70),
                            utc_now_iso(),
                        ),
                    )
                    conn.execute(
                        """
                        UPDATE sources
                        SET base_url = ?, type = ?, enabled = ?, priority = ?, credibility_score = ?,
                            entertainment_bias_score = ?
                        WHERE name = ?
                        """,
                        (
                            source["base_url"],
                            source["type"],
                            default_enabled,
                            source.get("priority", 50),
                            source.get("credibility_score", 70),
                            source.get("entertainment_bias_score", 70),
                            source["name"],
                        ),
                    )
            for entity in DEFAULT_TRACKED_ENTITIES:
                if self.is_postgres:
                    conn.execute(
                        """
                        INSERT INTO tracked_entities
                        (name, entity_type, aliases_json, is_active, created_at)
                        VALUES (%s, 'person', %s, TRUE, %s)
                        ON CONFLICT (name) DO NOTHING
                        """,
                        (entity["name"], Json(entity["aliases"]), utc_now_iso()),
                    )
                else:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO tracked_entities
                        (name, entity_type, aliases_json, is_active, created_at)
                        VALUES (?, 'person', ?, 1, ?)
                        """,
                        (entity["name"], json.dumps(entity["aliases"], ensure_ascii=False), utc_now_iso()),
                    )

    def get_enabled_sources(self) -> list[Any]:
        with self.connect() as conn:
            if self.is_postgres:
                return list(conn.execute("SELECT * FROM sources WHERE enabled = TRUE ORDER BY priority DESC, id"))
            return list(conn.execute("SELECT * FROM sources WHERE enabled = 1 ORDER BY priority DESC, id"))

    def get_tracked_entities(self) -> list[TrackedEntity]:
        with self.connect() as conn:
            if self.is_postgres:
                rows = conn.execute("SELECT * FROM tracked_entities WHERE is_active = TRUE ORDER BY name").fetchall()
            else:
                rows = conn.execute("SELECT * FROM tracked_entities WHERE is_active = 1 ORDER BY name").fetchall()
        return [
            TrackedEntity(
                id=int(row["id"]),
                name=row["name"],
                entity_type=row["entity_type"],
                aliases=row["aliases_json"] if isinstance(row["aliases_json"], list) else json.loads(row["aliases_json"]),
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]

    def source_id_by_name(self, name: str) -> int | None:
        with self.connect() as conn:
            if self.is_postgres:
                row = conn.execute("SELECT id FROM sources WHERE name = %s", (name,)).fetchone()
            else:
                row = conn.execute("SELECT id FROM sources WHERE name = ?", (name,)).fetchone()
        return int(row["id"]) if row else None

    def source_metadata_by_name(self, name: str) -> dict | None:
        with self.connect() as conn:
            if self.is_postgres:
                row = conn.execute(
                    """
                    SELECT id, name, base_url, type, priority, credibility_score, entertainment_bias_score
                    FROM sources
                    WHERE name = %s
                    """,
                    (name,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id, name, base_url, type, priority, credibility_score, entertainment_bias_score
                    FROM sources
                    WHERE name = ?
                    """,
                    (name,),
                ).fetchone()
        return dict(row) if row else None

    def insert_discovered_item(self, item: NormalizedItem, status: ItemStatus = ItemStatus.READY) -> int | None:
        with self.connect() as conn:
            try:
                if self.is_postgres:
                    cur = conn.execute(
                        """
                        INSERT INTO discovered_items (
                            source_id, title, url, canonical_url, published_at, raw_snippet, raw_body,
                            matched_entities_json, category, fingerprint, similarity_key, primary_entity,
                            relevance_score, relevance_explanation, is_primary_story, duplicate_group_id,
                            status, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            item.source_id,
                            item.title,
                            item.url,
                            item.canonical_url,
                            item.published_at.isoformat() if item.published_at else None,
                            item.raw_snippet,
                            item.raw_body,
                            Json(item.matched_entities),
                            item.category,
                            item.fingerprint,
                            item.similarity_key,
                            item.primary_entity,
                            item.relevance_score,
                            item.relevance_explanation,
                            item.is_primary_story,
                            item.duplicate_group_id,
                            status.value,
                            utc_now_iso(),
                        ),
                    )
                    row = cur.fetchone()
                    return int(row["id"]) if row else None

                cur = conn.execute(
                    """
                    INSERT INTO discovered_items (
                        source_id, title, url, canonical_url, published_at, raw_snippet, raw_body,
                        matched_entities_json, category, fingerprint, similarity_key, primary_entity,
                        relevance_score, relevance_explanation, is_primary_story, duplicate_group_id,
                        status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.source_id,
                        item.title,
                        item.url,
                        item.canonical_url,
                        item.published_at.isoformat() if item.published_at else None,
                        item.raw_snippet,
                        item.raw_body,
                        json.dumps(item.matched_entities, ensure_ascii=False),
                        item.category,
                        item.fingerprint,
                        item.similarity_key,
                        item.primary_entity,
                        item.relevance_score,
                        item.relevance_explanation,
                        1 if item.is_primary_story else 0,
                        item.duplicate_group_id,
                        status.value,
                        utc_now_iso(),
                    ),
                )
                return int(cur.lastrowid)
            except Exception:
                return None

    def reactivate_irrelevant_item(self, item: NormalizedItem, status: ItemStatus = ItemStatus.READY) -> int | None:
        with self.connect() as conn:
            if self.is_postgres:
                row = conn.execute(
                    """
                    SELECT id FROM discovered_items
                    WHERE (fingerprint = %s OR canonical_url = %s) AND status = %s
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    (item.fingerprint, item.canonical_url, ItemStatus.IRRELEVANT.value),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id FROM discovered_items
                    WHERE (fingerprint = ? OR canonical_url = ?) AND status = ?
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    (item.fingerprint, item.canonical_url, ItemStatus.IRRELEVANT.value),
                ).fetchone()
            if not row:
                return None
            item_id = int(row["id"])
            if self.is_postgres:
                conn.execute(
                    """
                    UPDATE discovered_items
                    SET source_id = %s, title = %s, url = %s, canonical_url = %s, published_at = %s,
                        raw_snippet = %s, raw_body = %s, matched_entities_json = %s, category = %s,
                        fingerprint = %s, similarity_key = %s, primary_entity = %s, relevance_score = %s,
                        relevance_explanation = %s, is_primary_story = %s, duplicate_group_id = NULL,
                        status = %s
                    WHERE id = %s
                    """,
                    (
                        item.source_id,
                        item.title,
                        item.url,
                        item.canonical_url,
                        item.published_at.isoformat() if item.published_at else None,
                        item.raw_snippet,
                        item.raw_body,
                        Json(item.matched_entities),
                        item.category,
                        item.fingerprint,
                        item.similarity_key,
                        item.primary_entity,
                        item.relevance_score,
                        item.relevance_explanation,
                        item.is_primary_story,
                        status.value,
                        item_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE discovered_items
                    SET source_id = ?, title = ?, url = ?, canonical_url = ?, published_at = ?,
                        raw_snippet = ?, raw_body = ?, matched_entities_json = ?, category = ?,
                        fingerprint = ?, similarity_key = ?, primary_entity = ?, relevance_score = ?,
                        relevance_explanation = ?, is_primary_story = ?, duplicate_group_id = NULL,
                        status = ?
                    WHERE id = ?
                    """,
                    (
                        item.source_id,
                        item.title,
                        item.url,
                        item.canonical_url,
                        item.published_at.isoformat() if item.published_at else None,
                        item.raw_snippet,
                        item.raw_body,
                        json.dumps(item.matched_entities, ensure_ascii=False),
                        item.category,
                        item.fingerprint,
                        item.similarity_key,
                        item.primary_entity,
                        item.relevance_score,
                        item.relevance_explanation,
                        1 if item.is_primary_story else 0,
                        status.value,
                        item_id,
                    ),
                )
            return item_id

    def mark_item_status(self, item_id: int, status: ItemStatus) -> None:
        with self.connect() as conn:
            if self.is_postgres:
                conn.execute("UPDATE discovered_items SET status = %s WHERE id = %s", (status.value, item_id))
            else:
                conn.execute("UPDATE discovered_items SET status = ? WHERE id = ?", (status.value, item_id))

    def requeue_failed_items(self) -> int:
        with self.connect() as conn:
            if self.is_postgres:
                cur = conn.execute(
                    "UPDATE discovered_items SET status = %s WHERE status = %s",
                    (ItemStatus.READY.value, ItemStatus.FAILED.value),
                )
                return int(cur.rowcount or 0)
            cur = conn.execute(
                "UPDATE discovered_items SET status = ? WHERE status = ?",
                (ItemStatus.READY.value, ItemStatus.FAILED.value),
            )
            return int(cur.rowcount or 0)

    def ready_items_for_publish(self, limit: int = 50) -> list[tuple[int, NormalizedItem]]:
        with self.connect() as conn:
            if self.is_postgres:
                rows = conn.execute(
                    """
                    SELECT di.*, s.name AS source_name
                    FROM discovered_items di
                    LEFT JOIN sources s ON s.id = di.source_id
                    LEFT JOIN published_posts pp ON pp.discovered_item_id = di.id
                    WHERE di.status = %s AND pp.id IS NULL
                    ORDER BY di.id ASC
                    LIMIT %s
                    """,
                    (ItemStatus.READY.value, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT di.*, s.name AS source_name
                    FROM discovered_items di
                    LEFT JOIN sources s ON s.id = di.source_id
                    LEFT JOIN published_posts pp ON pp.discovered_item_id = di.id
                    WHERE di.status = ? AND pp.id IS NULL
                    ORDER BY di.id ASC
                    LIMIT ?
                    """,
                    (ItemStatus.READY.value, limit),
                ).fetchall()
        out: list[tuple[int, NormalizedItem]] = []
        for row in rows:
            matched = row["matched_entities_json"]
            if isinstance(matched, str):
                matched_entities = json.loads(matched or "[]")
            else:
                matched_entities = matched or []
            published_raw = row["published_at"]
            published_at = None
            if published_raw:
                published_at = datetime.fromisoformat(str(published_raw))
            item = NormalizedItem(
                source_id=int(row["source_id"]) if row["source_id"] is not None else None,
                source_name=row["source_name"] or "Unknown Source",
                title=row["title"],
                url=row["url"],
                canonical_url=row["canonical_url"],
                published_at=published_at,
                raw_snippet=row["raw_snippet"] or "",
                raw_body=row["raw_body"] or "",
                matched_entities=list(matched_entities),
                category=row["category"],
                fingerprint=row["fingerprint"],
                similarity_key=row["similarity_key"],
                primary_entity=row["primary_entity"],
                relevance_score=int(row["relevance_score"] or 0),
                relevance_explanation=row["relevance_explanation"] or "",
                is_primary_story=bool(row["is_primary_story"]),
                duplicate_group_id=int(row["duplicate_group_id"]) if row["duplicate_group_id"] is not None else None,
            )
            out.append((int(row["id"]), item))
        return out

    def fingerprint_exists(self, fingerprint: str) -> bool:
        with self.connect() as conn:
            if self.is_postgres:
                row = conn.execute("SELECT 1 FROM discovered_items WHERE fingerprint = %s", (fingerprint,)).fetchone()
            else:
                row = conn.execute("SELECT 1 FROM discovered_items WHERE fingerprint = ?", (fingerprint,)).fetchone()
        return row is not None

    def item_id_by_fingerprint(self, fingerprint: str) -> int | None:
        with self.connect() as conn:
            if self.is_postgres:
                row = conn.execute("SELECT id FROM discovered_items WHERE fingerprint = %s", (fingerprint,)).fetchone()
            else:
                row = conn.execute("SELECT id FROM discovered_items WHERE fingerprint = ?", (fingerprint,)).fetchone()
        return int(row["id"]) if row else None

    def item_status_by_fingerprint(self, fingerprint: str) -> str | None:
        with self.connect() as conn:
            if self.is_postgres:
                row = conn.execute("SELECT status FROM discovered_items WHERE fingerprint = %s", (fingerprint,)).fetchone()
            else:
                row = conn.execute("SELECT status FROM discovered_items WHERE fingerprint = ?", (fingerprint,)).fetchone()
        return str(row["status"]) if row else None

    def canonical_url_exists(self, canonical_url: str) -> bool:
        with self.connect() as conn:
            if self.is_postgres:
                row = conn.execute("SELECT 1 FROM discovered_items WHERE canonical_url = %s", (canonical_url,)).fetchone()
            else:
                row = conn.execute("SELECT 1 FROM discovered_items WHERE canonical_url = ?", (canonical_url,)).fetchone()
        return row is not None

    def item_id_by_canonical_url(self, canonical_url: str) -> int | None:
        with self.connect() as conn:
            if self.is_postgres:
                row = conn.execute("SELECT id FROM discovered_items WHERE canonical_url = %s", (canonical_url,)).fetchone()
            else:
                row = conn.execute("SELECT id FROM discovered_items WHERE canonical_url = ?", (canonical_url,)).fetchone()
        return int(row["id"]) if row else None

    def item_status_by_canonical_url(self, canonical_url: str) -> str | None:
        with self.connect() as conn:
            if self.is_postgres:
                row = conn.execute("SELECT status FROM discovered_items WHERE canonical_url = %s", (canonical_url,)).fetchone()
            else:
                row = conn.execute("SELECT status FROM discovered_items WHERE canonical_url = ?", (canonical_url,)).fetchone()
        return str(row["status"]) if row else None

    def recent_similarity_keys(self, limit: int = 500) -> list[tuple[int, str, str]]:
        with self.connect() as conn:
            if self.is_postgres:
                rows = conn.execute(
                    "SELECT id, title, similarity_key FROM discovered_items ORDER BY id DESC LIMIT %s",
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, title, similarity_key FROM discovered_items ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [(int(row["id"]), row["title"], row["similarity_key"]) for row in rows]

    def create_run(self) -> int:
        with self.connect() as conn:
            if self.is_postgres:
                row = conn.execute("INSERT INTO system_runs (started_at) VALUES (%s) RETURNING id", (utc_now_iso(),)).fetchone()
                return int(row["id"])
            cur = conn.execute("INSERT INTO system_runs (started_at) VALUES (?)", (utc_now_iso(),))
            return int(cur.lastrowid)

    def finish_run(
        self,
        run_id: int,
        scanned_sources: int,
        discovered_count: int,
        relevant_count: int,
        published_count: int,
        error_count: int,
        notes: str = "",
    ) -> None:
        with self.connect() as conn:
            if self.is_postgres:
                conn.execute(
                    """
                    UPDATE system_runs
                    SET finished_at = %s, scanned_sources = %s, discovered_count = %s, relevant_count = %s,
                        published_count = %s, error_count = %s, notes = %s
                    WHERE id = %s
                    """,
                    (
                        utc_now_iso(),
                        scanned_sources,
                        discovered_count,
                        relevant_count,
                        published_count,
                        error_count,
                        notes,
                        run_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE system_runs
                    SET finished_at = ?, scanned_sources = ?, discovered_count = ?, relevant_count = ?,
                        published_count = ?, error_count = ?, notes = ?
                    WHERE id = ?
                    """,
                    (
                        utc_now_iso(),
                        scanned_sources,
                        discovered_count,
                        relevant_count,
                        published_count,
                        error_count,
                        notes,
                        run_id,
                    ),
                )

    def insert_published_post(
        self,
        discovered_item_id: int,
        telegram_message_id: int | None,
        telegram_chat_id: str | None,
        published_text: str,
        category: str,
        artist_main: str | None,
        source_name: str,
        post_type: str = "organic",
    ) -> None:
        with self.connect() as conn:
            if self.is_postgres:
                conn.execute(
                    """
                    INSERT INTO published_posts (
                        discovered_item_id, telegram_message_id, telegram_chat_id, published_text,
                        published_at, category, post_type, artist_main, source_name
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (discovered_item_id) DO NOTHING
                    """,
                    (
                        discovered_item_id,
                        telegram_message_id,
                        telegram_chat_id,
                        published_text,
                        utc_now_iso(),
                        category,
                        post_type,
                        artist_main,
                        source_name,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO published_posts (
                        discovered_item_id, telegram_message_id, telegram_chat_id, published_text,
                        published_at, category, post_type, artist_main, source_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        discovered_item_id,
                        telegram_message_id,
                        telegram_chat_id,
                        published_text,
                        utc_now_iso(),
                        category,
                        post_type,
                        artist_main,
                        source_name,
                    ),
                )

    def item_already_published(self, discovered_item_id: int) -> bool:
        with self.connect() as conn:
            if self.is_postgres:
                row = conn.execute(
                    "SELECT 1 FROM published_posts WHERE discovered_item_id = %s",
                    (discovered_item_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT 1 FROM published_posts WHERE discovered_item_id = ?",
                    (discovered_item_id,),
                ).fetchone()
        return row is not None

    def insert_ad_slot_post(
        self,
        telegram_message_id: int | None,
        telegram_chat_id: str | None,
        published_text: str,
    ) -> None:
        with self.connect() as conn:
            if self.is_postgres:
                conn.execute(
                    """
                    INSERT INTO published_posts (
                        discovered_item_id, telegram_message_id, telegram_chat_id, published_text,
                        published_at, category, post_type, artist_main, source_name
                    ) VALUES (NULL, %s, %s, %s, %s, 'money', 'ad_slot', NULL, 'UA Stars Money Bot')
                    """,
                    (telegram_message_id, telegram_chat_id, published_text, utc_now_iso()),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO published_posts (
                        discovered_item_id, telegram_message_id, telegram_chat_id, published_text,
                        published_at, category, post_type, artist_main, source_name
                    ) VALUES (NULL, ?, ?, ?, ?, 'money', 'ad_slot', NULL, 'UA Stars Money Bot')
                    """,
                    (telegram_message_id, telegram_chat_id, published_text, utc_now_iso()),
                )

    def published_post_count(self, post_type: str | None = "organic") -> int:
        with self.connect() as conn:
            if post_type is None:
                row = conn.execute("SELECT COUNT(*) AS count FROM published_posts").fetchone()
            else:
                if self.is_postgres:
                    row = conn.execute(
                        "SELECT COUNT(*) AS count FROM published_posts WHERE post_type = %s",
                        (post_type,),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT COUNT(*) AS count FROM published_posts WHERE post_type = ?",
                        (post_type,),
                    ).fetchone()
        return int(row["count"])
