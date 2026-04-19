from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
    telegram_admin_chat_id: str = ""
    openai_api_key: str = ""

    app_language: str = "uk"
    content_scope: str = "stars"
    dry_run: bool = True
    auto_publish: bool = False
    preview_mode: bool = False
    enable_instagram: bool = False
    instagram_export_dir: Path = Path("data/social/instagram")
    instagram_feed_url: str = ""
    instagram_handles_json: str = "{}"

    scan_interval_minutes: int = Field(default=15, ge=1)
    analytics_interval_hours: int = Field(default=24, ge=1)
    relevance_threshold: int = Field(default=60, ge=0, le=100)
    fuzzy_dup_threshold: int = Field(default=88, ge=0, le=100)
    ad_slot_every_n_posts: int = Field(default=0, ge=0)
    delayed_publish_seconds: int = Field(default=300, ge=0)
    max_publish_per_run: int = Field(default=3, ge=0)

    db_path: Path = Path("data/app.db")
    log_level: str = "INFO"
    http_timeout_seconds: int = Field(default=15, ge=1)
    user_agent: str = "UAStarsMoneyBot/1.0 (+https://telegram.org)"
    enable_openai: bool = False
    openai_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def get_settings() -> Settings:
    return Settings()
