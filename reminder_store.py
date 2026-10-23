"""재기동 후에도 복구할 수 있는 리마인더 저장소."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any

import storage


DATABASE_NAME = "reminders.sqlite3"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(storage.DATA_DIR / DATABASE_NAME, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize() -> None:
    storage.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS reminders ("
            "id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, "
            "message_id INTEGER NOT NULL, message_thread_id INTEGER, "
            "text TEXT NOT NULL, due_at REAL NOT NULL, "
            "next_attempt_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, "
            "sent_at REAL, UNIQUE (chat_id, message_id))"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS pending_reminders "
            "ON reminders (next_attempt_at) WHERE sent_at IS NULL"
        )


def add(
    *,
    chat_id: int,
    message_id: int,
    message_thread_id: int | None,
    text: str,
    due_at: float,
) -> dict[str, Any]:
    with _connect() as connection:
        # 재전달된 Telegram 업데이트로 같은 알림을 두 번 만들지 않는다.
        connection.execute(
            "INSERT INTO reminders "
            "(chat_id, message_id, message_thread_id, text, due_at, next_attempt_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(chat_id, message_id) DO NOTHING",
            (chat_id, message_id, message_thread_id, text, due_at, due_at),
        )
        row = connection.execute(
            "SELECT * FROM reminders WHERE chat_id = ? AND message_id = ?",
            (chat_id, message_id),
        ).fetchone()
        return dict(row)


def get_next() -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM reminders WHERE sent_at IS NULL "
            "ORDER BY next_attempt_at, id LIMIT 1"
        ).fetchone()
        return dict(row) if row is not None else None


def mark_sent(reminder_id: int, sent_at: float) -> None:
    with _connect() as connection:
        connection.execute(
            "UPDATE reminders SET sent_at = ? WHERE id = ? AND sent_at IS NULL",
            (sent_at, reminder_id),
        )


def postpone(reminder_id: int, retry_at: float) -> None:
    with _connect() as connection:
        connection.execute(
            "UPDATE reminders SET next_attempt_at = ?, attempts = attempts + 1 "
            "WHERE id = ? AND sent_at IS NULL",
            (retry_at, reminder_id),
        )
