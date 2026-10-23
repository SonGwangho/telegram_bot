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
    "/r 1시간 50분 노트북 챙기기\n"
    "/r {example_date} 09:00 회의\n"
    "/r {example_short_date} 09:00 회의\n"
    "/r {example_month}월 {example_day}일 09:00 회의\n"
    "/r {example_month}월 {example_day}일 9시 30분 회의\n\n"
    "분·시간은 1 이상의 정수로 입력해 주세요.\n"
    "날짜는 YYYY-MM-DD, MM-DD, MM월 DD일 형식으로 입력해 주세요.\n"
    "날짜 뒤에는 HH:MM 또는 H시 M분 형식의 시각을 붙여 주세요.\n"
    "연도를 생략하면 올해로 해석하며, 지난 날짜·시각은 등록하지 않습니다.\n"
    "모든 시간은 한국 시간 기준입니다.\n"
    "알림 시간이 되면 등록한 메시지에 답장해드립니다.\n"
    "봇이 꺼져 있는 동안 시간이 지난 알림은 재기동 후 보내드립니다."
)
_RELATIVE_TIME = re.compile(r"([0-9]+)(분|시간)")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_SHORT_DATE = re.compile(r"([0-9]{1,2})-([0-9]{1,2})")
_KOREAN_DATE = re.compile(r"([0-9]{1,2})월\s*([0-9]{1,2})일")
_TIME = re.compile(r"[0-9]{2}:[0-9]{2}")
_KOREAN_TIME = re.compile(r"([0-9]{1,2})시\s*([0-9]{1,2})분")
_STORAGE_ERRORS = (OSError, sqlite3.Error)


class ReminderError(ValueError):
    """리마인더 입력이 올바르지 않을 때 발생한다."""


def get_usage() -> str:
    tomorrow = datetime.now(SEOUL_TIMEZONE).date() + timedelta(days=1)
    return USAGE.format(
        example_date=tomorrow.isoformat(),
        example_short_date=tomorrow.strftime("%m-%d"),
        example_month=tomorrow.month,
        example_day=tomorrow.day,
    )


def parse_reminder(
    args: list[str], *, now: datetime | None = None
) -> tuple[datetime, str]:
    now = datetime.now(SEOUL_TIMEZONE) if now is None else now.astimezone(SEOUL_TIMEZONE)
    if not args:
        raise ReminderError("시간과 알림 내용을 입력해 주세요.")

    relative = _RELATIVE_TIME.fullmatch(args[0])
    if relative:
        seconds = 0
        content_start = 0
        try:
            for token in args:
                relative = _RELATIVE_TIME.fullmatch(token)
                if relative is None:
                    break
                amount = int(relative[1])
                if amount <= 0:
                    raise ReminderError("분·시간은 1 이상의 정수로 입력해 주세요.")
                seconds += amount * (60 if relative[2] == "분" else 3600)
                content_start += 1
            due_at = now + timedelta(seconds=seconds)
        except ReminderError:
            raise
        except (OverflowError, ValueError) as error:
            raise ReminderError("분·시간은 계산 가능한 범위의 양의 정수로 입력해 주세요.") from error
    else:
        date_text = args[0]
        time_index = 1
        if not _DATE.fullmatch(date_text):
            short_date = _SHORT_DATE.fullmatch(date_text)
            if short_date:
                month, day = short_date.groups()
            else:
                korean_date = _KOREAN_DATE.fullmatch(date_text)
                if korean_date is None:
                    korean_date = _KOREAN_DATE.fullmatch(" ".join(args[:2]))
                    time_index = 2
                if korean_date is None:
                    raise ReminderError("시간은 분·시간 또는 날짜와 시각 형식으로 입력해 주세요.")
                month, day = korean_date.groups()
            date_text = f"{now.year}-{month}-{day}"
        if len(args) <= time_index:
            raise ReminderError("날짜 뒤에 HH:MM 또는 H시 M분 형식의 시각을 입력해 주세요.")
        time_text = args[time_index]
        content_start = time_index + 1
        if not _TIME.fullmatch(time_text):
            korean_time = _KOREAN_TIME.fullmatch(time_text)
            if korean_time is None:
                korean_time = _KOREAN_TIME.fullmatch(" ".join(args[time_index:time_index + 2]))
                content_start = time_index + 2
            if korean_time is None:
                raise ReminderError("날짜 뒤에 HH:MM 또는 H시 M분 형식의 시각을 입력해 주세요.")
            hour, minute = korean_time.groups()
            time_text = f"{int(hour):02d}:{int(minute):02d}"
        try:
            due_at = datetime.strptime(
                f"{date_text} {time_text}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=SEOUL_TIMEZONE)
        except ValueError as error:
            raise ReminderError("존재하는 날짜와 시각을 입력해 주세요.") from error
        if due_at <= now:
            raise ReminderError("현재보다 미래의 날짜와 시각을 입력해 주세요.")

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
