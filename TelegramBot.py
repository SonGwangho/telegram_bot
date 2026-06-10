from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Optional

from telegram import Bot, InputFile, InputMediaAudio, InputMediaDocument, InputMediaPhoto, InputMediaVideo
from telegram.constants import ChatAction, ParseMode
from telegram.error import NetworkError, RetryAfter, TelegramError, TimedOut

from config import telegram_token


logger = logging.getLogger(__name__)


class TelegramBot:
    """텔레그램 Bot API 공통 기능을 감싼 기본 래퍼 클래스."""

    def __init__(
        self,
        token: Optional[str] = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        error_message: str = "오류가 발생했어요.",
    ) -> None:
        self.token = token or telegram_token
        self.bot = Bot(token=self.token)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.error_message = error_message

    async def get_me(self) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.get_me(),
            notify_on_error=False,
        )

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str | None = ParseMode.HTML,
        disable_web_page_preview: bool = True,
        reply_markup: Any | None = None,
    ) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
                reply_markup=reply_markup,
            ),
            chat_id=chat_id,
            notify_on_error=True,
        )

    async def reply_message(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: Any | None = None,
    ) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_to_message_id=message_id,
                reply_markup=reply_markup,
            ),
            chat_id=chat_id,
            notify_on_error=True,
        )

    async def send_photo(
        self,
        chat_id: int | str,
        photo: str | bytes | Path,
        caption: str | None = None,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: Any | None = None,
    ) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.send_photo(
                chat_id=chat_id,
                photo=self._prepare_file(photo),
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            ),
            chat_id=chat_id,
            notify_on_error=True,
        )

    async def send_document(
        self,
        chat_id: int | str,
        document: str | bytes | Path,
        caption: str | None = None,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: Any | None = None,
    ) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.send_document(
                chat_id=chat_id,
                document=self._prepare_file(document),
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            ),
            chat_id=chat_id,
            notify_on_error=True,
        )

    async def send_audio(
        self,
        chat_id: int | str,
        audio: str | bytes | Path,
        caption: str | None = None,
        parse_mode: str | None = ParseMode.HTML,
        performer: str | None = None,
        title: str | None = None,
    ) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.send_audio(
                chat_id=chat_id,
                audio=self._prepare_file(audio),
                caption=caption,
                parse_mode=parse_mode,
                performer=performer,
                title=title,
            ),
            chat_id=chat_id,
            notify_on_error=True,
        )

    async def send_video(
        self,
        chat_id: int | str,
        video: str | bytes | Path,
        caption: str | None = None,
        parse_mode: str | None = ParseMode.HTML,
        supports_streaming: bool = True,
    ) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.send_video(
                chat_id=chat_id,
                video=self._prepare_file(video),
                caption=caption,
                parse_mode=parse_mode,
                supports_streaming=supports_streaming,
            ),
            chat_id=chat_id,
            notify_on_error=True,
        )

    async def send_media_group(
        self,
        chat_id: int | str,
        media_items: Iterable[dict[str, Any]],
    ) -> Any:
        media_group = []
        media_map = {
            "photo": InputMediaPhoto,
            "video": InputMediaVideo,
            "document": InputMediaDocument,
            "audio": InputMediaAudio,
        }

        for item in media_items:
            media_type = item["type"]
            media_class = media_map.get(media_type)
            if media_class is None:
                raise ValueError(f"지원하지 않는 미디어 타입입니다: {media_type}")

            media_group.append(
                media_class(
                    media=self._prepare_file(item["media"]),
                    caption=item.get("caption"),
                    parse_mode=item.get("parse_mode", ParseMode.HTML),
                )
            )

        return await self._request_with_retry(
            lambda: self.bot.send_media_group(chat_id=chat_id, media=media_group),
            chat_id=chat_id,
            notify_on_error=True,
        )

    async def send_chat_action(
        self,
        chat_id: int | str,
        action: str = ChatAction.TYPING,
    ) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.send_chat_action(chat_id=chat_id, action=action),
            notify_on_error=False,
        )

    async def forward_message(
        self,
        chat_id: int | str,
        from_chat_id: int | str,
        message_id: int,
    ) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.forward_message(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
            ),
            chat_id=chat_id,
            notify_on_error=True,
        )

    async def copy_message(
        self,
        chat_id: int | str,
        from_chat_id: int | str,
        message_id: int,
        caption: str | None = None,
        parse_mode: str | None = ParseMode.HTML,
    ) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                caption=caption,
                parse_mode=parse_mode,
            ),
            chat_id=chat_id,
            notify_on_error=True,
        )

    async def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: Any | None = None,
    ) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            ),
            chat_id=chat_id,
            notify_on_error=True,
        )

    async def edit_message_caption(
        self,
        chat_id: int | str,
        message_id: int,
        caption: str,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: Any | None = None,
    ) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            ),
            chat_id=chat_id,
            notify_on_error=True,
        )

    async def delete_message(self, chat_id: int | str, message_id: int) -> bool:
        return await self._request_with_retry(
            lambda: self.bot.delete_message(chat_id=chat_id, message_id=message_id),
            notify_on_error=False,
        )

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool:
        return await self._request_with_retry(
            lambda: self.bot.answer_callback_query(
                callback_query_id=callback_query_id,
                text=text,
                show_alert=show_alert,
            ),
            notify_on_error=False,
        )

    async def get_file(self, file_id: str) -> Any:
        return await self._request_with_retry(
            lambda: self.bot.get_file(file_id),
            notify_on_error=False,
        )

    async def download_file(self, file_id: str, destination: str | Path) -> Path:
        telegram_file = await self.get_file(file_id)
        destination_path = Path(destination)
        await self._request_with_retry(
            lambda: telegram_file.download_to_drive(custom_path=str(destination_path)),
            notify_on_error=False,
        )
        return destination_path

    async def close(self) -> None:
        await self.bot.session.close()

    async def _request_with_retry(
        self,
        api_call: Callable[[], Awaitable[Any]],
        *,
        chat_id: int | str | None = None,
        notify_on_error: bool = False,
    ) -> Any:
        last_error: TelegramError | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await api_call()
            except RetryAfter as error:
                last_error = error
                if attempt >= self.max_retries:
                    break

                await asyncio.sleep(self._retry_after_delay(error))
            except (TimedOut, NetworkError) as error:
                last_error = error
                if attempt >= self.max_retries:
                    break

                await asyncio.sleep(self.retry_delay * (attempt + 1))
            except TelegramError as error:
                last_error = error
                break

        self._log_api_error(last_error)

        if notify_on_error and chat_id is not None:
            await self._send_error_message(chat_id)
            return None

        if last_error is not None:
            raise last_error

        return None

    async def _send_error_message(self, chat_id: int | str) -> Any:
        for attempt in range(2):
            try:
                return await self.bot.send_message(
                    chat_id=chat_id,
                    text=self.error_message,
                    parse_mode=None,
                    disable_web_page_preview=True,
                )
            except RetryAfter as error:
                if attempt >= 1:
                    self._log_api_error(error)
                    return None

                await asyncio.sleep(self._retry_after_delay(error))
            except (TimedOut, NetworkError) as error:
                if attempt >= 1:
                    self._log_api_error(error)
                    return None

                await asyncio.sleep(self.retry_delay)
            except TelegramError as error:
                self._log_api_error(error)
                return None

        return None

    def _retry_after_delay(self, error: RetryAfter) -> float:
        retry_after = error.retry_after
        if hasattr(retry_after, "total_seconds"):
            return float(retry_after.total_seconds()) + 0.2

        return float(retry_after) + 0.2

    def _log_api_error(self, error: TelegramError | None) -> None:
        if error is None:
            logger.warning("Telegram API request failed without an exception.")
            return

        logger.warning(
            "Telegram API request failed.",
            exc_info=(type(error), error, error.__traceback__),
        )

    def _prepare_file(self, file_source: str | bytes | Path) -> Any:
        if isinstance(file_source, bytes):
            return file_source

        path = Path(file_source)
        if path.exists():
            return InputFile(path.open("rb"))

        return file_source
