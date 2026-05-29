from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from uuid import uuid4

from google import genai

from config import gemini_api_key, gemini_model, gemini_model_lite

try:
    from config import gemini_backup_dir, gemini_data_file
except ImportError:
    gemini_data_file = "data/gemini_history.json"
    gemini_backup_dir = "data/backups"


class GeminiBot:
    """Gemini text generation helper with local history, backup, and restore."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        data_file: str | Path | None = None,
        backup_dir: str | Path | None = None,
    ) -> None:
        self.api_key = api_key or gemini_api_key
        self.model = model or gemini_model_lite
        self.data_file = Path(data_file or gemini_data_file)
        self.backup_dir = Path(backup_dir or gemini_backup_dir)
        self.client = genai.Client(api_key=self.api_key)

        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def generate_text(
        self,
        prompt: str,
        *,
        save: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        text = response.text or ""

        if save:
            self.save_record(
                prompt=prompt,
                response=text,
                metadata=metadata,
            )

        return text

    async def generate_text_async(
        self,
        prompt: str,
        *,
        save: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return await asyncio.to_thread(
            self.generate_text,
            prompt,
            save=save,
            metadata=metadata,
        )

    def generate_fortune(
        self,
        name: str = "",
        birthdate: str = "",
        question: str = "",
        *,
        save: bool = True,
    ) -> str:
        prompt = self.build_fortune_prompt(
            name=name,
            birthdate=birthdate,
            question=question,
        )
        return self.generate_text(
            prompt,
            save=save,
            metadata={
                "type": "fortune",
                "name": name,
                "birthdate": birthdate,
                "question": question,
            },
        )

    async def generate_fortune_async(
        self,
        name: str = "",
        birthdate: str = "",
        question: str = "",
        *,
        save: bool = True,
    ) -> str:
        return await asyncio.to_thread(
            self.generate_fortune,
            name,
            birthdate,
            question,
            save=save,
        )

    def build_fortune_prompt(
        self,
        name: str = "",
        birthdate: str = "",
        question: str = "",
    ) -> str:
        name_text = name or "user"
        birthdate_text = birthdate or "unknown"
        question_text = question or "오늘의 종합 운세"

        return f"""
너는 운세 상담가야.
답변은 한국어로 작성해줘.

사용자 정보:
- 이름: {name_text}
- 생년월일: {birthdate_text}
- 질문: {question_text}

응답 형식:
1. 오늘의 흐름
2. 조심할 점
3. 작은 조언

규칙:
- 300자 이내로 답변할 것.
""".strip()

    def load_records(self) -> list[dict[str, Any]]:
        if not self.data_file.exists() or self.data_file.stat().st_size == 0:
            return []

        with self.data_file.open("r", encoding="utf-8") as file:
            try:
                data = json.load(file)
            except JSONDecodeError:
                return []

        if isinstance(data, list):
            return data

        return []

    def save_records(self, records: list[dict[str, Any]]) -> None:
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.data_file.with_suffix(f"{self.data_file.suffix}.tmp")

        with temp_file.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)

        temp_file.replace(self.data_file)

    def save_record(
        self,
        *,
        prompt: str,
        response: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        records = self.load_records()
        record = {
            "id": uuid4().hex,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "model": self.model,
            "prompt": prompt,
            "response": response,
            "metadata": metadata or {},
        }
        records.append(record)
        self.save_records(records)
        return record

    def backup_data(self) -> Path:
        if not self.data_file.exists():
            self.save_records([])

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"{self.data_file.stem}_{timestamp}.json"
        shutil.copy2(self.data_file, backup_file)
        return backup_file

    def restore_data(self, backup_file: str | Path) -> Path:
        source = Path(backup_file)
        if not source.exists():
            raise FileNotFoundError(f"Backup file not found: {source}")

        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, self.data_file)
        return self.data_file

    def list_backups(self) -> list[Path]:
        if not self.backup_dir.exists():
            return []

        return sorted(self.backup_dir.glob("*.json"), reverse=True)


gemini_bot = GeminiBot()
