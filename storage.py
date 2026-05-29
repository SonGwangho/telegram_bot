from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any


DATA_DIR = Path("data")


def create(name: str, jsonData: Any | None = None) -> Any:
    path = _get_json_path(name)
    if path.exists():
        raise FileExistsError(f"JSON file already exists: {path}")

    data = {} if jsonData is None else jsonData
    _write_json(path, data)
    return data


def update(name: str, jsonData: Any) -> Any:
    path = _get_json_path(name)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    _write_json(path, jsonData)
    return jsonData


def remove(name: str) -> None:
    path = _get_json_path(name)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    path.unlink()


def get(name: str) -> Any:
    path = _get_json_path(name)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    return _read_json(path)


def isExist(name: str) -> bool:
    return _get_json_path(name).exists()


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
