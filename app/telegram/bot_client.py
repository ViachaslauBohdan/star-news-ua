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
        image_url: str | None = None,
    ) -> TelegramPublishResult:
        if self.dry_run or not self._bot:
            return TelegramPublishResult(sent=False, dry_run=True, text=text, chat_id=chat_id)

        reply_markup = None
        if source_url:
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Більше в джерелі", url=source_url)]])

        if image_url:
            try:
                message = await self._bot.send_photo(
                    chat_id=chat_id,
                    photo=image_url,
                    caption=self._photo_caption(text, source_url),
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            except Exception:
                # Some source images are blocked/unreachable by Telegram.
                # Fall back to a plain text post so one bad media URL does not block the queue.
                message = await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                    reply_markup=reply_markup,
                )
        else:
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

    def _photo_caption(self, text: str, source_url: str | None = None) -> str:
        if len(text) <= 1024:
            return text
        suffix = f'\n\n<a href="{source_url}">Більше в джерелі</a>' if source_url else ""
        limit = 1024 - len(suffix) - 3
        return text[: max(limit, 0)].rstrip() + "..." + suffix
