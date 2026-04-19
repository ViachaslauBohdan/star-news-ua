from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class SourceType(StrEnum):
    RSS = "rss"
    HTML = "html"


class ItemStatus(StrEnum):
    DISCOVERED = "discovered"
    IRRELEVANT = "irrelevant"
    DUPLICATE = "duplicate"
    READY = "ready"
    PUBLISHED = "published"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class RawItem(BaseModel):
    source_name: str
    source_url: str
    title: str
    url: str
    published_at: datetime | None = None
    snippet: str = ""
    raw_body: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedItem(BaseModel):
    source_id: int | None = None
    source_name: str
    title: str
    url: str
    canonical_url: str
    published_at: datetime | None = None
    raw_snippet: str = ""
    raw_body: str = ""
    matched_entities: list[str] = Field(default_factory=list)
    category: str = "other"
    fingerprint: str
    similarity_key: str
    primary_entity: str | None = None
    relevance_score: int = 0
    relevance_explanation: str = ""
    is_primary_story: bool = True
    duplicate_group_id: int | None = None


class TrackedEntity(BaseModel):
    id: int | None = None
    name: str
    entity_type: str = "person"
    aliases: list[str] = Field(default_factory=list)
    is_active: bool = True


class RelevanceResult(BaseModel):
    is_relevant: bool
    matched_entities: list[str] = Field(default_factory=list)
    main_entity: str | None = None
    category: str = "other"
    relevance_score: int = 0
    reasons: list[str] = Field(default_factory=list)


class RewriteResult(BaseModel):
    text: str
    hook: str
    short_title: str
    hashtags: list[str] = Field(default_factory=list)


class TelegramPublishResult(BaseModel):
    sent: bool
    message_id: int | None = None
    chat_id: str | None = None
    dry_run: bool = False
    text: str
