from __future__ import annotations

import asyncio
import json
import random
import shutil
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from uuid import uuid4

from google import genai
from google.genai import errors as genai_errors

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
        # self.model = model or gemini_model
        self.model = model or gemini_model_lite
        self.data_file = Path(data_file or gemini_data_file)
        self.backup_dir = Path(backup_dir or gemini_backup_dir)
        self.client = genai.Client(api_key=self.api_key)

        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def generate_text(
        self,
        prompt: str,
        model_type: str | None = None,
        *,
        save: bool = True,
        metadata: dict[str, Any] | None = None,
        history_limit: int = 5,
    ) -> str:
        selected_model = model_type or self.model

        new_prompt = self.build_chat_prompt(
            prompt=prompt,
            metadata=metadata,
            history_limit=history_limit,
        )

        try:
            response = self.client.models.generate_content(
                model=selected_model,
                contents=new_prompt,
            )
            text = response.text or ""
        except genai_errors.APIError:
            text = "제미나이 API 에러"
            save = False

        if save:
            self.save_record(
                prompt=prompt,
                response=text,
                model=selected_model,
                metadata=metadata,
            )

        return text

    async def generate_text_async(
        self,
        prompt: str,
        model_type: str | None = None,
        *,
        save: bool = True,
        metadata: dict[str, Any] | None = None,
        history_limit: int = 5,
    ) -> str:
        return await asyncio.to_thread(
            self.generate_text,
            prompt,
            model_type,
            save=save,
            metadata=metadata,
            history_limit=history_limit,
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
            model_type = gemini_model,
            save=save,
            history_limit=0,
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
        name_text = name.strip() or "사용자"
        birthdate_text = birthdate.strip() or "미상"
        question_text = question.strip() or "오늘의 종합 운세"

        return f"""
너는 따뜻하고 차분한 한국어 운세 상담가다.
사용자가 가볍게 즐길 수 있는 오늘의 운세를 작성해라.

운세는 오늘날짜와 사용자 생년월일을 이용하여 사용자 사주를 기준으로 판단한다.
사주를 기준으로 오늘의 운세를 상위 ??%로 표현해라.
운세는 사주팔자, 주역, 오행 같은 전통 운세 느낌.
생년월일은 YYYYMMDD 기준으로 제공된다.

[오늘의 운세 지표]

[사용자 정보]
이름: {name_text}
생년월일: {birthdate_text}
질문: {question_text}

[응답 형식]
오늘의 운세는 상위 ??% 입니다.

1. 오늘의 흐름:
2. 조심할 점:
3. 작은 조언:

[규칙]
- 300자 이내
- 한국어로만 답변
- 사주팔자, 주역, 오행 같은 전통 운세 느낌을 살짝 섞기
- 현실적인 조언도 함께 넣기
""".strip()
    
    def build_chat_prompt(
        self,
        *,
        prompt: str,
        metadata: dict[str, Any] | None = None,
        history_limit: int = 5,
    ) -> str:
        history = self.get_user_chat_history(metadata=metadata, limit=history_limit)
        history_text = self.format_chat_history(history)

        if history_text:
            return f"""
너는 한국어로 답변하는 AI야.
반드시 500자 이내로 답변해.
아래 이전 대화는 같은 사용자와 나눈 대화야. 필요한 경우에만 참고해.

이전 대화:
{history_text}

사용자 질문:{prompt}
""".strip()

        return f"""
너는 한국어로 답변하는 AI야.
반드시 500자 이내로 답변해.

사용자 질문:{prompt}
""".strip()

    def get_user_chat_history(
        self,
        *,
        metadata: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        user_id = (metadata or {}).get("user_id")
        if not user_id or limit <= 0:
            return []

        user_id = str(user_id)
        records = self.load_records()
        history = [
            record
            for record in records
            if str(record.get("metadata", {}).get("user_id")) == user_id
            and record.get("metadata", {}).get("type", "chat") == "chat"
        ]
        return history[-limit:]

    @staticmethod
    def format_chat_history(records: list[dict[str, Any]]) -> str:
        lines = []
        for record in records:
            prompt = str(record.get("prompt", "")).strip()
            response = str(record.get("response", "")).strip()
            if not prompt or not response:
                continue

            lines.append(f"사용자: {prompt}")
            lines.append(f"AI: {response}")

        return "\n".join(lines)

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
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        records = self.load_records()
        record = {
            "id": uuid4().hex,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "model": model or self.model,
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
