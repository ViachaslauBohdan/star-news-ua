from __future__ import annotations

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from app.models import TelegramPublishResult


class TelegramBotClient:
    def __init__(self, token: str, dry_run: bool = True):
        self.token = token
        self.dry_run = dry_run
        self._bot: Bot | None = Bot(token=token) if token and not dry_run else None

    async def send_message(
        self,
        chat_id: str,
        text: str,
        source_url: str | None = None,
    ) -> TelegramPublishResult:
        if self.dry_run or not self._bot:
            return TelegramPublishResult(sent=False, dry_run=True, text=text, chat_id=chat_id)

        reply_markup = None
        if source_url:
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Читати джерело", url=source_url)]])

        message = await self._bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
            reply_markup=reply_markup,
        )
        return TelegramPublishResult(
            sent=True,
            message_id=message.message_id,
            chat_id=str(message.chat_id),
            dry_run=False,
            text=text,
        )
