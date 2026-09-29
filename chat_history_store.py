"""채팅 기록을 메시지 단위로 저장하고, 기존 JSON을 최초 한 번 이관한다."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import storage


LEGACY_HISTORY_NAME = "chat_room_history"
DATABASE_NAME = f"{LEGACY_HISTORY_NAME}.sqlite3"
_SCHEMA_VERSION = 1
_initialization_lock = threading.Lock()


def save_message(
    *,
    chat_id: int | str,
    chat_name: str,
    chat_type: str,
    message: dict[str, Any],
    max_messages: int,
) -> None:
    chat_key = str(chat_id)
    metadata = _encode({
        "chat_id": chat_id,
        "chat_name": chat_name,
        "chat_type": chat_type,
    })
    payload = _encode(message)
    message_key = _message_key(message)

    with _connect(max_messages) as connection, connection:
        # 조회와 갱신 사이에 다른 쓰기가 끼어 중복 메시지가 생기지 않게 한다.
        connection.execute("BEGIN IMMEDIATE")
        _save_chat(connection, chat_key, metadata)
        existing = None
        if message_key is not None:
            existing = connection.execute(
                "SELECT sequence FROM messages WHERE chat_key = ? AND message_key = ? "
                "ORDER BY sequence DESC LIMIT 1",
                (chat_key, message_key),
            ).fetchone()

        if existing is None:
            connection.execute(
                "INSERT INTO messages (chat_key, message_key, payload) VALUES (?, ?, ?)",
                (chat_key, message_key, payload),
            )
        else:
            # 수정 메시지는 원래 순서를 유지한다.
            connection.execute(
                "UPDATE messages SET payload = ? WHERE sequence = ?",
                (payload, existing[0]),
            )

        connection.execute(
            "DELETE FROM messages WHERE chat_key = ? AND sequence <= ("
            "SELECT sequence FROM messages WHERE chat_key = ? "
            "ORDER BY sequence DESC LIMIT 1 OFFSET ?)",
            (chat_key, chat_key, max_messages),
        )


def get_recent_messages(
    chat_id: int | str, *, limit: int, max_messages: int
) -> list[dict[str, Any]]:
    with _connect(max_messages) as connection:
        rows = connection.execute(
            "SELECT payload FROM messages WHERE chat_key = ? "
            "ORDER BY sequence DESC LIMIT ?",
            (str(chat_id), limit),
        ).fetchall()
    return [json.loads(row[0]) for row in reversed(rows)]


@contextmanager
def _connect(max_messages: int) -> Iterator[sqlite3.Connection]:
    path = storage.DATA_DIR / DATABASE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        _initialize(connection, max_messages)
        yield connection
    finally:
        connection.close()


def _initialize(connection: sqlite3.Connection, max_messages: int) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version == _SCHEMA_VERSION:
        return
    if version != 0:
        raise ValueError("지원하지 않는 채팅 기록 DB 버전입니다.")

    with _initialization_lock:
        # 최초 요청이 동시에 들어와도 이관은 한 번만 수행한다.
        if connection.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION:
            return
        connection.execute("PRAGMA journal_mode = WAL")
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION:
                return
            connection.execute(
                "CREATE TABLE chats (chat_key TEXT PRIMARY KEY, metadata TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE messages ("
                "sequence INTEGER PRIMARY KEY, "
                "chat_key TEXT NOT NULL REFERENCES chats(chat_key), "
                "message_key TEXT, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX messages_by_chat ON messages (chat_key, sequence DESC)"
            )
            connection.execute(
                "CREATE INDEX messages_by_id ON messages "
                "(chat_key, message_key, sequence DESC)"
            )
            _import_legacy_json(connection, max_messages)
            # 이관과 완료 표시는 같은 트랜잭션으로 확정한다. JSON은 그대로 둔다.
            connection.execute("PRAGMA user_version = 1")


def _import_legacy_json(connection: sqlite3.Connection, max_messages: int) -> None:
    if not storage.isExist(LEGACY_HISTORY_NAME):
        return
    cache = storage.get(LEGACY_HISTORY_NAME)
    if not isinstance(cache, dict):
        raise ValueError("채팅 기록 JSON의 최상위 값은 객체여야 합니다.")

    for chat_key, chat in cache.items():
        if not isinstance(chat, dict):
            continue
        metadata = {key: value for key, value in chat.items() if key != "messages"}
        _save_chat(connection, chat_key, _encode(metadata))
        raw_messages = chat.get("messages")
        if not isinstance(raw_messages, list):
            continue
        messages = [item for item in raw_messages if isinstance(item, dict)]
        connection.executemany(
            "INSERT INTO messages (chat_key, message_key, payload) VALUES (?, ?, ?)",
            [
                (chat_key, _message_key(message), _encode(message))
                for message in messages[-max_messages:]
            ],
        )


def _save_chat(connection: sqlite3.Connection, chat_key: str, metadata: str) -> None:
    connection.execute(
        "INSERT INTO chats (chat_key, metadata) VALUES (?, ?) "
        "ON CONFLICT(chat_key) DO UPDATE SET metadata = excluded.metadata",
        (chat_key, metadata),
    )


def _message_key(message: dict[str, Any]) -> str | None:
    message_id = message.get("message_id")
    return None if message_id is None else _encode(message_id)


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
