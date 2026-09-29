from __future__ import annotations

import json
import threading
from json import JSONDecodeError
from pathlib import Path
from typing import Any


DATA_DIR = Path("data")
_locks_guard = threading.Lock()
_file_locks: dict[Path, Any] = {}


def _lock_for(path: Path) -> Any:
    # 다른 JSON 파일의 입출력은 서로 기다리지 않는다.
    # resolve()는 Windows에서 파일 생성 중 \\?\ 접두사가 달라질 수 있다.
    key = path.absolute()
    with _locks_guard:
        return _file_locks.setdefault(key, threading.RLock())


def create(name: str, jsonData: Any | None = None) -> Any:
    path = _get_json_path(name)
    with _lock_for(path):
        if path.exists():
            raise FileExistsError(f"JSON file already exists: {path}")

        data = {} if jsonData is None else jsonData
        _write_json(path, data)
        return data


def update(name: str, jsonData: Any) -> Any:
    path = _get_json_path(name)
    with _lock_for(path):
        if not path.exists():
            raise FileNotFoundError(f"JSON file not found: {path}")

        _write_json(path, jsonData)
        return jsonData


def get_or_create(name: str) -> Any:
    """파일이 없으면 빈 객체로 생성한다. 존재 확인과 생성을 함께 잠근다."""
    path = _get_json_path(name)
    with _lock_for(path):
        if path.exists():
            return _read_json(path)
        _write_json(path, {})
        return {}


def update_entry(name: str, key: str, value: Any) -> None:
    """최신 파일의 한 항목만 바꿔 다른 사용자가 저장한 내용을 보존한다.

    잠금은 현재 봇 프로세스 안에서 유효하다. 같은 key의 요청 순서는
    update_processor가 보장하며, 파일 전체를 읽고 쓰는 동안만 잠근다.
    """
    path = _get_json_path(name)
    with _lock_for(path):
        data = _read_json(path) if path.exists() else {}
        if not isinstance(data, dict):
            raise ValueError(f"JSON root must be an object: {path}")
        data[key] = value
        _write_json(path, data)


def remove(name: str) -> None:
    path = _get_json_path(name)
    with _lock_for(path):
        if not path.exists():
            raise FileNotFoundError(f"JSON file not found: {path}")

        path.unlink()


def get(name: str) -> Any:
    path = _get_json_path(name)
    with _lock_for(path):
        if not path.exists():
            raise FileNotFoundError(f"JSON file not found: {path}")

        return _read_json(path)


def isExist(name: str) -> bool:
    path = _get_json_path(name)
    with _lock_for(path):
        return path.exists()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")

    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    temp_path.replace(path)


def _read_json(path: Path) -> Any:
    if path.stat().st_size == 0:
        return {}

    with path.open("r", encoding="utf-8") as file:
        try:
            return json.load(file)
        except JSONDecodeError as error:
            raise ValueError(f"Invalid JSON file: {path}") from error


def _get_json_path(name: str) -> Path:
    if not name or Path(name).name != name:
        raise ValueError("name must be a file name, not a path.")

    stem = name.removesuffix(".json")
    if not stem:
        raise ValueError("name cannot be empty.")

    return DATA_DIR / f"{stem}.json"
