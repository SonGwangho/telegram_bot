"""Gemini 대화 기록의 SQLite 저장, 사용자별 조회, JSON 이관·백업을 담당한다."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


logger = logging.getLogger(__name__)
_initialization_lock = threading.Lock()
_SCHEMA_VERSION = 1
_INSERT_RECORD = (
    "INSERT INTO records (user_id, chat_id, is_chat, payload) VALUES (?, ?, ?, ?)"
)


class GeminiHistoryStore:
    def __init__(self, legacy_file: Path) -> None:
        self.legacy_file = legacy_file
        # 설정된 JSON 경로와 절대로 같아지지 않게 확장자를 덧붙인다.
        self.database_file = legacy_file.with_name(legacy_file.name + ".sqlite3")

    def recent(self, metadata: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
        if limit <= 0 or not str(metadata.get("user_id") or ""):
            return []
        condition, parameters = self._chat_filter(metadata)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload FROM records WHERE {condition} "
                "ORDER BY sequence DESC LIMIT ?",
                (*parameters, limit),
            ).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]

    def clear_chat(self, metadata: dict[str, Any]) -> int:
        if not str(metadata.get("user_id") or ""):
            return 0
        condition, parameters = self._chat_filter(metadata)
        with self._connect() as connection, connection:
            result = connection.execute(
                f"DELETE FROM records WHERE {condition}", parameters
            )
            return result.rowcount

    def load_all(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM records ORDER BY sequence"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def append(self, record: dict[str, Any], *, max_records: int) -> None:
        if max_records < 1:
            raise ValueError("max_records는 1 이상이어야 합니다.")
        row = self._record_row(record)
        with self._connect() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(_INSERT_RECORD, row)
            connection.execute(
                "DELETE FROM records WHERE sequence <= ("
                "SELECT sequence FROM records ORDER BY sequence DESC LIMIT 1 OFFSET ?)",
                (max_records,),
            )

    def replace(self, records: list[dict[str, Any]]) -> None:
        # 기존 load_records()처럼 객체가 아닌 항목은 제외한다.
        records = [record for record in records if isinstance(record, dict)]
        rows = [self._record_row(record) for record in records]
        with self._connect(initial_records=records) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM records")
            connection.executemany(_INSERT_RECORD, rows)

    def export_json(self, destination: Path) -> None:
        records = self.load_all()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=destination.parent,
                prefix=destination.name + ".", suffix=".tmp", delete=False,
            ) as file:
                temporary = Path(file.name)
                json.dump(records, file, ensure_ascii=False, indent=2)
            temporary.replace(destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @contextmanager
    def _connect(
        self, *, initial_records: list[dict[str, Any]] | None = None
    ) -> Iterator[sqlite3.Connection]:
        self.database_file.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_file, timeout=10)
        try:
            self._initialize(connection, initial_records)
            yield connection
        finally:
            connection.close()

    def _initialize(
        self, connection: sqlite3.Connection,
        initial_records: list[dict[str, Any]] | None,
    ) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == _SCHEMA_VERSION:
            return
        if version != 0:
            raise ValueError("지원하지 않는 Gemini 기록 DB 버전입니다.")

        with _initialization_lock:
            if connection.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION:
                return
            connection.execute("PRAGMA journal_mode = WAL")
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION:
                    return
                connection.execute(
                    "CREATE TABLE records (sequence INTEGER PRIMARY KEY, "
                    "user_id TEXT NOT NULL, chat_id TEXT NOT NULL, "
                    "is_chat INTEGER NOT NULL, payload TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE INDEX records_by_chat ON records "
                    "(is_chat, user_id, chat_id, sequence DESC)"
                )
                connection.execute(
                    "CREATE INDEX records_by_user ON records "
                    "(is_chat, user_id, sequence DESC)"
                )
                # 명시적 복원은 손상된 원본 JSON이 있어도 가능하게 한다.
                records = self._read_legacy() if initial_records is None else initial_records
                connection.executemany(
                    _INSERT_RECORD, [self._record_row(record) for record in records]
                )
                connection.execute("PRAGMA user_version = 1")

    def _read_legacy(self) -> list[dict[str, Any]]:
        if not self.legacy_file.exists() or self.legacy_file.stat().st_size == 0:
            return []
        try:
            with self.legacy_file.open("r", encoding="utf-8") as file:
                records = json.load(file)
            if not isinstance(records, list):
                raise ValueError("Gemini 기록 JSON의 최상위 값은 배열이어야 합니다.")
        except (OSError, ValueError):
            # 빈 기록으로 이관을 완료하지 않는다. 원본을 보존하고 재시도한다.
            logger.exception("Failed to migrate Gemini history JSON: %s", self.legacy_file)
            raise
        return [record for record in records if isinstance(record, dict)]

    @staticmethod
    def _record_row(record: dict[str, Any]) -> tuple[str, str, int, str]:
        metadata = record.get("metadata")
        valid_metadata = isinstance(metadata, dict)
        metadata = metadata if valid_metadata else {}
        return (
            str(metadata.get("user_id") or ""),
            str(metadata.get("chat_id") or ""),
            int(valid_metadata and metadata.get("type", "chat") == "chat"),
            json.dumps(record, ensure_ascii=False, separators=(",", ":")),
        )

    @staticmethod
    def _chat_filter(metadata: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
        condition = "is_chat = 1 AND user_id = ?"
        parameters = (str(metadata.get("user_id") or ""),)
        if metadata.get("chat_id") is not None:
            condition += " AND chat_id = ?"
            parameters += (str(metadata["chat_id"]),)
        return condition, parameters
