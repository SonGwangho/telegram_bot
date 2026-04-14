from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional

from telegram import Bot, InputFile, InputMediaAudio, InputMediaDocument, InputMediaPhoto, InputMediaVideo
from telegram.constants import ChatAction, ParseMode

from config import telegram_token


class TelegramBot:
    """텔레그램 Bot API 공통 기능을 감싼 기본 래퍼 클래스."""

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or telegram_token
        self.bot = Bot(token=self.token)

    async def get_me(self) -> Any:
        return await self.bot.get_me()

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str | None = ParseMode.HTML,
        disable_web_page_preview: bool = True,
        reply_markup: Any | None = None,
    ) -> Any:
        return await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            reply_markup=reply_markup,
        )

    async def reply_message(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: Any | None = None,
    ) -> Any:
        return await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_to_message_id=message_id,
            reply_markup=reply_markup,
        )

    async def send_photo(
        self,
        chat_id: int | str,
        photo: str | bytes | Path,
        caption: str | None = None,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: Any | None = None,
    ) -> Any:
        return await self.bot.send_photo(
            chat_id=chat_id,
            photo=self._prepare_file(photo),
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )

    async def send_document(
        self,
        chat_id: int | str,
        document: str | bytes | Path,
        caption: str | None = None,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: Any | None = None,
    ) -> Any:
        return await self.bot.send_document(
            chat_id=chat_id,
            document=self._prepare_file(document),
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
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
        return await self.bot.send_audio(
            chat_id=chat_id,
            audio=self._prepare_file(audio),
            caption=caption,
            parse_mode=parse_mode,
            performer=performer,
            title=title,
        )

    async def send_video(
        self,
        chat_id: int | str,
        video: str | bytes | Path,
        caption: str | None = None,
        parse_mode: str | None = ParseMode.HTML,
        supports_streaming: bool = True,
    ) -> Any:
        return await self.bot.send_video(
            chat_id=chat_id,
            video=self._prepare_file(video),
            caption=caption,
            parse_mode=parse_mode,
            supports_streaming=supports_streaming,
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

        return await self.bot.send_media_group(chat_id=chat_id, media=media_group)

    async def send_chat_action(
        self,
        chat_id: int | str,
        action: str = ChatAction.TYPING,
    ) -> Any:
        return await self.bot.send_chat_action(chat_id=chat_id, action=action)

    async def forward_message(
        self,
        chat_id: int | str,
        from_chat_id: int | str,
        message_id: int,
    ) -> Any:
        return await self.bot.forward_message(
            chat_id=chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
        )

    async def copy_message(
        self,
        chat_id: int | str,
        from_chat_id: int | str,
        message_id: int,
        caption: str | None = None,
        parse_mode: str | None = ParseMode.HTML,
    ) -> Any:
        return await self.bot.copy_message(
            chat_id=chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            caption=caption,
            parse_mode=parse_mode,
        )

    async def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: Any | None = None,
    ) -> Any:
        return await self.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )

    async def edit_message_caption(
        self,
        chat_id: int | str,
        message_id: int,
        caption: str,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: Any | None = None,
    ) -> Any:
        return await self.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )

    async def delete_message(self, chat_id: int | str, message_id: int) -> bool:
        return await self.bot.delete_message(chat_id=chat_id, message_id=message_id)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool:
        return await self.bot.answer_callback_query(
            callback_query_id=callback_query_id,
            text=text,
            show_alert=show_alert,
        )

    async def get_file(self, file_id: str) -> Any:
        return await self.bot.get_file(file_id)

    async def download_file(self, file_id: str, destination: str | Path) -> Path:
        telegram_file = await self.bot.get_file(file_id)
        destination_path = Path(destination)
        await telegram_file.download_to_drive(custom_path=str(destination_path))
        return destination_path

    async def close(self) -> None:
        await self.bot.session.close()

    def _prepare_file(self, file_source: str | bytes | Path) -> Any:
        if isinstance(file_source, bytes):
            return file_source

        path = Path(file_source)
        if path.exists():
            return InputFile(path.open("rb"))

        return file_source
