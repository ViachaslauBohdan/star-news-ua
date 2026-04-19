from __future__ import annotations

import asyncio

from app.config import Settings
from app.db import Database
from app.models import ItemStatus, NormalizedItem, RewriteResult, TelegramPublishResult
from app.services.formatter import TelegramFormatter
from app.telegram.bot_client import TelegramBotClient


class Publisher:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self.formatter = TelegramFormatter()
        self.client = TelegramBotClient(settings.telegram_bot_token, dry_run=settings.dry_run)

    async def publish(self, item_id: int, item: NormalizedItem, rewrite: RewriteResult) -> TelegramPublishResult:
        if self.db.item_already_published(item_id):
            return TelegramPublishResult(sent=False, dry_run=self.settings.dry_run, text="", chat_id=None)

        text = self.formatter.format_post(item, rewrite)
        if self.settings.delayed_publish_seconds:
            await asyncio.sleep(self.settings.delayed_publish_seconds)

        target_chat = self._target_chat()
        result = await self.client.send_message(target_chat, text, source_url=item.url)
        self.db.insert_published_post(
            discovered_item_id=item_id,
            telegram_message_id=result.message_id,
            telegram_chat_id=result.chat_id or target_chat,
            published_text=text,
            category=item.category,
            artist_main=item.matched_entities[0] if item.matched_entities else None,
            source_name=item.source_name,
        )
        self.db.mark_item_status(item_id, ItemStatus.PUBLISHED if self.settings.auto_publish else ItemStatus.NEEDS_REVIEW)
        await self._maybe_publish_ad_slot(target_chat)
        return result

    def _target_chat(self) -> str:
        if self.settings.auto_publish:
            return self.settings.telegram_channel_id
        return self.settings.telegram_admin_chat_id or self.settings.telegram_channel_id

    async def _maybe_publish_ad_slot(self, target_chat: str) -> None:
        cadence = self.settings.ad_slot_every_n_posts
        if cadence <= 0:
            return
        organic_count = self.db.published_post_count("organic")
        if organic_count == 0 or organic_count % cadence != 0:
            return
        text = self.formatter.format_ad_slot()
        result = await self.client.send_message(target_chat, text)
        self.db.insert_ad_slot_post(result.message_id, result.chat_id or target_chat, text)
