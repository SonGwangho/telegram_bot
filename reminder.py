"""고정 형식 시간 파싱과 영속 리마인더 전송 작업."""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from telegram import Bot
from telegram.error import RetryAfter, TelegramError

from TelegramBot import TelegramBot
import reminder_store


logger = logging.getLogger(__name__)
SEOUL_TIMEZONE = timezone(timedelta(hours=9))
SERVICE_KEY = "reminder_service"
USAGE = (
    "⏰ 리마인더 사용법\n\n"
    "/r 30분 빨래 꺼내기\n"
    "/r 2시간 약 먹기\n"
    "/r {example_date} 09:00 회의\n\n"
    "분·시간은 1 이상의 정수로 입력해 주세요.\n"
    "날짜 지정은 YYYY-MM-DD HH:MM 형식이며 한국 시간 기준입니다.\n"
    "알림 시간이 되면 등록한 메시지에 답장해드립니다.\n"
    "봇이 꺼져 있는 동안 시간이 지난 알림은 재기동 후 보내드립니다."
)
_RELATIVE_TIME = re.compile(r"([0-9]+)(분|시간)")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TIME = re.compile(r"[0-9]{2}:[0-9]{2}")
_STORAGE_ERRORS = (OSError, sqlite3.Error)


class ReminderError(ValueError):
    """리마인더 입력이 올바르지 않을 때 발생한다."""


def get_usage() -> str:
    tomorrow = datetime.now(SEOUL_TIMEZONE).date() + timedelta(days=1)
    return USAGE.format(example_date=tomorrow.isoformat())


def parse_reminder(
    args: list[str], *, now: datetime | None = None
) -> tuple[datetime, str]:
    now = datetime.now(SEOUL_TIMEZONE) if now is None else now.astimezone(SEOUL_TIMEZONE)
    if not args:
        raise ReminderError("시간과 알림 내용을 입력해 주세요.")

    relative = _RELATIVE_TIME.fullmatch(args[0])
    if relative:
        try:
            amount = int(relative[1])
            seconds = amount * (60 if relative[2] == "분" else 3600)
            due_at = now + timedelta(seconds=seconds)
        except (OverflowError, ValueError) as error:
            raise ReminderError("분·시간은 계산 가능한 범위의 양의 정수로 입력해 주세요.") from error
        if amount <= 0:
            raise ReminderError("분·시간은 1 이상의 정수로 입력해 주세요.")
        content_start = 1
    elif len(args) >= 2 and _DATE.fullmatch(args[0]) and _TIME.fullmatch(args[1]):
        try:
            due_at = datetime.strptime(
                f"{args[0]} {args[1]}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=SEOUL_TIMEZONE)
        except ValueError as error:
            raise ReminderError("존재하는 날짜와 시각을 입력해 주세요.") from error
        if due_at <= now:
            raise ReminderError("현재보다 미래의 날짜와 시각을 입력해 주세요.")
        content_start = 2
    else:
        raise ReminderError("시간은 30분, 2시간 또는 YYYY-MM-DD HH:MM 형식으로 입력해 주세요.")

    text = " ".join(args[content_start:]).strip()
    if not text:
        raise ReminderError("알림 내용을 입력해 주세요.")
    # 이모지까지 포함해 Telegram 메시지 길이 제한 안에 여유를 둔다.
    if len(text.encode("utf-16-le")) // 2 > 4000:
        raise ReminderError("알림 내용이 너무 길어요. 4,000자 이내로 줄여 주세요.")
    return due_at, text


def format_due_at(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, SEOUL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


class ReminderService:
    def __init__(self, bot: Bot) -> None:
        # 재시도 시각은 DB에 기록하므로 전송 래퍼 내부에서는 재시도하지 않는다.
        self._telegram = TelegramBot(bot=bot, max_retries=0)
        self._wakeup = asyncio.Event()
        self._stopping = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await asyncio.to_thread(reminder_store.initialize)
        # Application.create_task는 stop()에서 작업 종료를 기다리므로,
        # post_stop에서 직접 종료할 장기 작업은 별도로 관리한다.
        self._task = asyncio.create_task(self._run(), name="reminder-worker")

    async def stop(self) -> None:
        self._stopping = True
        self._wakeup.set()
        if self._task is not None:
            await self._task

    async def register(
        self, *, chat_id: int, message_id: int, message_thread_id: int | None,
        due_at: datetime, text: str,
    ) -> dict[str, Any]:
        if self._task is None or self._task.done() or self._stopping:
            raise RuntimeError("리마인더 전송 작업이 실행 중이 아닙니다.")
        reminder = await asyncio.to_thread(
            reminder_store.add,
            chat_id=chat_id,
            message_id=message_id,
            message_thread_id=message_thread_id,
            text=text,
            due_at=due_at.timestamp(),
        )
        self._wakeup.set()
        return reminder

    async def _wait(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._wakeup.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _run(self) -> None:
        while not self._stopping:
            self._wakeup.clear()
            try:
                reminder = await asyncio.to_thread(reminder_store.get_next)
                if reminder is None:
                    await self._wait(60)
                    continue
                delay = reminder["next_attempt_at"] - time.time()
                if delay > 0:
                    await self._wait(min(delay, 60))
                    continue
                if not self._stopping:
                    await self._deliver(reminder)
            except Exception:
                logger.exception("Reminder worker failed; retrying in five seconds.")
                await self._wait(5)

    async def _deliver(self, reminder: dict[str, Any]) -> None:
        try:
            await self._telegram.reply_message(
                chat_id=reminder["chat_id"],
                message_id=reminder["message_id"],
                text=f"⏰ {reminder['text']}",
                parse_mode=None,
                message_thread_id=reminder["message_thread_id"],
                allow_sending_without_reply=True,
                notify_on_error=False,
            )
        except TelegramError as error:
            delay = min(60 * 2 ** min(reminder["attempts"], 6), 3600)
            if isinstance(error, RetryAfter):
                retry_after = error.retry_after
                delay = max(delay, (
                    retry_after.total_seconds() if isinstance(retry_after, timedelta)
                    else float(retry_after)
                ) + 1)
            logger.warning("Reminder delivery failed; scheduled for retry.")
            await asyncio.to_thread(
                reminder_store.postpone, reminder["id"], time.time() + delay
            )
            return

        # 전송 성공 후 저장에 실패해도 같은 프로세스에서는 다시 전송하지 않는다.
        while True:
            try:
                await asyncio.to_thread(reminder_store.mark_sent, reminder["id"], time.time())
                return
            except _STORAGE_ERRORS:
                logger.exception("Failed to record reminder delivery; retrying the save.")
                if self._stopping:
                    return
                await asyncio.sleep(5)
