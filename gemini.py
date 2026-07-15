from __future__ import annotations

import asyncio
import json
import logging
import shutil
import threading
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from uuid import uuid4

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from config import (
    gemini_api_key,
    gemini_backup_dir,
    gemini_data_file,
    gemini_model,
    gemini_model_lite,
)


logger = logging.getLogger(__name__)

DEFAULT_DATA_FILE = "data/gemini_history.json"
DEFAULT_BACKUP_DIR = "data/backups"
API_ERROR_PREFIX = "제미나이 API 에러"
CONFIG_ERROR_PREFIX = "제미나이 설정 에러"
MAX_CHAT_RESPONSE_CHARS = 3_500
MAX_FORTUNE_RESPONSE_CHARS = 1_000

CHAT_SYSTEM_INSTRUCTION = """
# 사용자 정보
- 사용자는 시스템 엔지니어이자 개발자이자 코더이다.
- 사용자는 한국에 산다.
- 사용자는 20대 후반에서 30대 중반까지 분포한다.

# 너는 텔레그램 봇에서 동작하는 한국어 AI 도우미다.
- 사용자의 질문 의도를 먼저 파악하고 핵심부터 답한다.
- 사실과 추정을 구분하고, 확실하지 않은 내용은 모른다고 말한다.
- 이전 대화는 맥락으로만 참고하고 현재 질문을 우선한다.
- 반드시 HTML 태그, 마크다운 문법을 활용한 강조 없이 600자 이내의 일반 텍스트로 답한다.
- 사용자 정보를 가볍게 참고하여 답한다.
- 질문이 불분명하면 추가 질문을 통해 명확히 한다.
- 대답을 가능한 유머러스하고 따뜻하게 한다.
- 반드시 문장을 완성한다.
""".strip()

FORTUNE_SYSTEM_INSTRUCTION = """
너는 한국어로 답하는 오늘의 운세 안내자다.
- 운세는 가볍게 참고할 오락성 내용으로 작성한다.
- 확정적인 예언, 공포를 유발하는 표현, 의료·법률·재정 결정을 유도하는 표현은 피한다.
- 제공된 날짜와 생년월일을 참고해 전통 운세의 분위기와 현실적인 조언을 함께 담는다.
- 좋은 점과 조심할 점을 균형 있게 안내하고, 내용 전체에 일관성을 가진다.
- 반드시 HTML 태그, 마크다운 문법을 활용한 강조 없이 600자 이내의 일반 텍스트로 답한다.
""".strip()


class GeminiConfigurationError(RuntimeError):
    """Raised when required Gemini configuration is missing."""


class EmptyGeminiResponse(RuntimeError):
    """Raised when Gemini returns no usable text."""


class GeminiBot:
    """Gemini text generation helper with isolated local conversation history."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        lite_model: str | None = None,
        data_file: str | Path | None = None,
        backup_dir: str | Path | None = None,
        *,
        client: Any | None = None,
        max_history_records: int = 2_000,
    ) -> None:
        if max_history_records < 1:
            raise ValueError("max_history_records는 1 이상이어야 합니다.")

        self.api_key = api_key or gemini_api_key
        self.model = model or gemini_model or gemini_model_lite
        self.lite_model = lite_model or gemini_model_lite or self.model
        self.data_file = Path(data_file or gemini_data_file or DEFAULT_DATA_FILE)
        self.backup_dir = Path(backup_dir or gemini_backup_dir or DEFAULT_BACKUP_DIR)
        self.max_history_records = max_history_records

        self._client = client
        self._client_lock = threading.Lock()
        self._records_lock = threading.RLock()

        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    @property
    def client(self) -> Any:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    if not self.api_key:
                        raise GeminiConfigurationError(
                            "gemini_api_key가 설정되지 않았습니다."
                        )
                    self._client = genai.Client(
                        api_key=self.api_key,
                        http_options=types.HttpOptions(
                            timeout=30_000,
                            retry_options=types.HttpRetryOptions(
                                attempts=3,
                                initial_delay=0.5,
                                max_delay=4.0,
                                exp_base=2.0,
                                jitter=0.2,
                                http_status_codes=[
                                    408,
                                    429,
                                    500,
                                    502,
                                    503,
                                    504,
                                ],
                            ),
                        ),
                    )
        return self._client

    @staticmethod
    def is_error_response(text: str) -> bool:
        return text.startswith((API_ERROR_PREFIX, CONFIG_ERROR_PREFIX))

    def generate_text(
        self,
        prompt: str,
        model_type: str | None = None,
        *,
        save: bool = True,
        metadata: dict[str, Any] | None = None,
        history_limit: int = 5,
    ) -> str:
        normalized_prompt = self._normalize_prompt(prompt)
        contents = self.build_chat_contents(
            prompt=normalized_prompt,
            metadata=metadata,
            history_limit=history_limit,
        )
        return self._generate_sync(
            prompt=normalized_prompt,
            contents=contents,
            requested_model=model_type,
            allow_lite_fallback=model_type is None,
            system_instruction=CHAT_SYSTEM_INSTRUCTION,
            temperature=0.4,
            max_output_tokens=1_024,
            max_response_chars=MAX_CHAT_RESPONSE_CHARS,
            save=save,
            metadata=metadata,
        )

    async def generate_text_async(
        self,
        prompt: str,
        model_type: str | None = None,
        *,
        save: bool = True,
        metadata: dict[str, Any] | None = None,
        history_limit: int = 5,
    ) -> str:
        normalized_prompt = self._normalize_prompt(prompt)
        contents = await asyncio.to_thread(
            self.build_chat_contents,
            prompt=normalized_prompt,
            metadata=metadata,
            history_limit=history_limit,
        )
        return await self._generate_async(
            prompt=normalized_prompt,
            contents=contents,
            requested_model=model_type,
            allow_lite_fallback=model_type is None,
            system_instruction=CHAT_SYSTEM_INSTRUCTION,
            temperature=0.4,
            max_output_tokens=1_024,
            max_response_chars=MAX_CHAT_RESPONSE_CHARS,
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
        metadata: dict[str, Any] | None = None,
    ) -> str:
        prompt = self.build_fortune_prompt(
            name=name,
            birthdate=birthdate,
            question=question,
        )
        record_metadata = self._fortune_metadata(
            metadata=metadata,
            name=name,
            birthdate=birthdate,
            question=question,
        )
        return self._generate_sync(
            prompt=prompt,
            contents=[self._content("user", prompt)],
            requested_model=self.lite_model,
            allow_lite_fallback=False,
            system_instruction=FORTUNE_SYSTEM_INSTRUCTION,
            temperature=0.8,
            max_output_tokens=512,
            max_response_chars=MAX_FORTUNE_RESPONSE_CHARS,
            save=save,
            metadata=record_metadata,
        )

    async def generate_fortune_async(
        self,
        name: str = "",
        birthdate: str = "",
        question: str = "",
        *,
        save: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        prompt = self.build_fortune_prompt(
            name=name,
            birthdate=birthdate,
            question=question,
        )
        record_metadata = self._fortune_metadata(
            metadata=metadata,
            name=name,
            birthdate=birthdate,
            question=question,
        )
        return await self._generate_async(
            prompt=prompt,
            contents=[self._content("user", prompt)],
            requested_model=self.lite_model,
            allow_lite_fallback=False,
            system_instruction=FORTUNE_SYSTEM_INSTRUCTION,
            temperature=0.8,
            max_output_tokens=512,
            max_response_chars=MAX_FORTUNE_RESPONSE_CHARS,
            save=save,
            metadata=record_metadata,
        )

    def _generate_sync(
        self,
        *,
        prompt: str,
        contents: list[types.Content],
        requested_model: str | None,
        allow_lite_fallback: bool,
        system_instruction: str,
        temperature: float,
        max_output_tokens: int,
        max_response_chars: int,
        save: bool,
        metadata: dict[str, Any] | None,
    ) -> str:
        try:
            models = self._model_candidates(
                requested_model,
                allow_lite_fallback=allow_lite_fallback,
            )
            config = self._generation_config(
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        except GeminiConfigurationError as error:
            return f"{CONFIG_ERROR_PREFIX} - {error}"

        last_error: Exception | None = None
        for selected_model in models:
            try:
                response = self.client.models.generate_content(
                    model=selected_model,
                    contents=contents,
                    config=config,
                )
                text = self._extract_text(response, max_response_chars)
            except GeminiConfigurationError as error:
                return f"{CONFIG_ERROR_PREFIX} - {error}"
            except genai_errors.APIError as error:
                last_error = error
                self._log_api_error(selected_model, error)
                continue
            except Exception as error:
                last_error = error
                logger.exception("Gemini request failed: model=%s", selected_model)
                break

            if save:
                self.save_record(
                    prompt=prompt,
                    response=text,
                    model=selected_model,
                    metadata=metadata,
                )
            return text

        return f"{API_ERROR_PREFIX} - {last_error}"

    async def _generate_async(
        self,
        *,
        prompt: str,
        contents: list[types.Content],
        requested_model: str | None,
        allow_lite_fallback: bool,
        system_instruction: str,
        temperature: float,
        max_output_tokens: int,
        max_response_chars: int,
        save: bool,
        metadata: dict[str, Any] | None,
    ) -> str:
        try:
            models = self._model_candidates(
                requested_model,
                allow_lite_fallback=allow_lite_fallback,
            )
            config = self._generation_config(
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        except GeminiConfigurationError as error:
            return f"{CONFIG_ERROR_PREFIX} - {error}"

        last_error: Exception | None = None
        for selected_model in models:
            try:
                response = await self.client.aio.models.generate_content(
                    model=selected_model,
                    contents=contents,
                    config=config,
                )
                text = self._extract_text(response, max_response_chars)
            except GeminiConfigurationError as error:
                return f"{CONFIG_ERROR_PREFIX} - {error}"
            except genai_errors.APIError as error:
                last_error = error
                self._log_api_error(selected_model, error)
                continue
            except Exception as error:
                last_error = error
                logger.exception("Gemini async request failed: model=%s", selected_model)
                break

            if save:
                await asyncio.to_thread(
                    self.save_record,
                    prompt=prompt,
                    response=text,
                    model=selected_model,
                    metadata=metadata,
                )
            return text

        return f"{API_ERROR_PREFIX} - {last_error}"

    def build_fortune_prompt(
        self,
        name: str = "",
        birthdate: str = "",
        question: str = "",
    ) -> str:
        today = datetime.now().strftime("%Y년 %m월 %d일")
        name_text = name.strip() or "사용자"
        birthdate_text = birthdate.strip() or "미상"
        question_text = question.strip() or "오늘의 종합 운세"

        return f"""
[기준 날짜]
{today}

[사용자 정보]
이름: {name_text}
생년월일(YYYYMMDD): {birthdate_text}
질문: {question_text}

[응답 형식]
첫 줄: {today} {name_text}님의 운세입니다.
오늘의 운세와 그에따른 조언, 재치있는 한 줄의 격언을 포함한다.
""".strip()

    def build_chat_contents(
        self,
        *,
        prompt: str,
        metadata: dict[str, Any] | None = None,
        history_limit: int = 5,
    ) -> list[types.Content]:
        history = self.get_user_chat_history(metadata=metadata, limit=history_limit)
        contents: list[types.Content] = []

        for record in history:
            previous_prompt = str(record.get("prompt", "")).strip()
            previous_response = str(record.get("response", "")).strip()
            if not previous_prompt or not previous_response:
                continue
            contents.append(self._content("user", previous_prompt))
            contents.append(self._content("model", previous_response))

        contents.append(self._content("user", prompt))
        return contents

    def build_chat_prompt(
        self,
        *,
        prompt: str,
        metadata: dict[str, Any] | None = None,
        history_limit: int = 5,
    ) -> str:
        """Return a readable prompt representation for compatibility and debugging."""

        history = self.get_user_chat_history(metadata=metadata, limit=history_limit)
        history_text = self.format_chat_history(history)
        if history_text:
            return f"{CHAT_SYSTEM_INSTRUCTION}\n\n이전 대화:\n{history_text}\n\n현재 질문:\n{prompt}"
        return f"{CHAT_SYSTEM_INSTRUCTION}\n\n현재 질문:\n{prompt}"

    def get_user_chat_history(
        self,
        *,
        metadata: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        user_id = str((metadata or {}).get("user_id") or "")
        if not user_id:
            return []

        records = self.load_records()
        history = [
            record
            for record in records
            if self._matches_chat(record, metadata or {})
        ]
        return history[-limit:]

    @staticmethod
    def format_chat_history(records: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for record in records:
            prompt = str(record.get("prompt", "")).strip()
            response = str(record.get("response", "")).strip()
            if not prompt or not response:
                continue
            lines.append(f"사용자: {prompt}")
            lines.append(f"AI: {response}")
        return "\n".join(lines)

    def clear_chat_history(self, *, metadata: dict[str, Any]) -> int:
        if not str(metadata.get("user_id") or ""):
            return 0

        with self._records_lock:
            records = self._load_records_unlocked()
            remaining = [
                record
                for record in records
                if not self._matches_chat(record, metadata)
            ]
            deleted_count = len(records) - len(remaining)
            if deleted_count:
                self._save_records_unlocked(remaining)
            return deleted_count

    def load_records(self) -> list[dict[str, Any]]:
        with self._records_lock:
            return self._load_records_unlocked()

    def _load_records_unlocked(self) -> list[dict[str, Any]]:
        if not self.data_file.exists() or self.data_file.stat().st_size == 0:
            return []

        try:
            with self.data_file.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except JSONDecodeError:
            self._backup_corrupt_history()
            logger.exception("Gemini history JSON is invalid: %s", self.data_file)
            return []
        except OSError:
            logger.exception("Gemini history could not be read: %s", self.data_file)
            return []

        if not isinstance(data, list):
            logger.error("Gemini history root is not a list: %s", self.data_file)
            return []
        return [record for record in data if isinstance(record, dict)]

    def save_records(self, records: list[dict[str, Any]]) -> None:
        with self._records_lock:
            self._save_records_unlocked(records)

    def _save_records_unlocked(self, records: list[dict[str, Any]]) -> None:
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
        record = {
            "id": uuid4().hex,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "model": model or self.model,
            "prompt": prompt,
            "response": response,
            "metadata": metadata or {},
        }

        with self._records_lock:
            records = self._load_records_unlocked()
            records.append(record)
            records = records[-self.max_history_records :]
            self._save_records_unlocked(records)
        return record

    def backup_data(self) -> Path:
        with self._records_lock:
            if not self.data_file.exists():
                self._save_records_unlocked([])

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_file = self.backup_dir / f"{self.data_file.stem}_{timestamp}.json"
            shutil.copy2(self.data_file, backup_file)
            return backup_file

    def restore_data(self, backup_file: str | Path) -> Path:
        source = Path(backup_file)
        if not source.exists():
            raise FileNotFoundError(f"Backup file not found: {source}")

        try:
            with source.open("r", encoding="utf-8") as file:
                restored_data = json.load(file)
        except JSONDecodeError as error:
            raise ValueError(f"Invalid backup JSON: {source}") from error
        if not isinstance(restored_data, list):
            raise ValueError(f"Backup root must be a list: {source}")

        with self._records_lock:
            self._save_records_unlocked(restored_data)
        return self.data_file

    def list_backups(self) -> list[Path]:
        if not self.backup_dir.exists():
            return []
        return sorted(self.backup_dir.glob("*.json"), reverse=True)

    async def close(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.aio.aclose()
        finally:
            self._client.close()

    def _model_candidates(
        self,
        requested_model: str | None,
        *,
        allow_lite_fallback: bool,
    ) -> list[str]:
        selected_model = (requested_model or self.model or "").strip()
        if not selected_model:
            raise GeminiConfigurationError(
                "gemini_model 또는 gemini_model_lite가 설정되지 않았습니다."
            )

        models = [selected_model]
        fallback_model = (self.lite_model or "").strip()
        if allow_lite_fallback and fallback_model and fallback_model not in models:
            models.append(fallback_model)
        return models

    @staticmethod
    def _generation_config(
        *,
        system_instruction: str,
        temperature: float,
        max_output_tokens: int,
    ) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="text/plain",
        )

    @staticmethod
    def _content(role: str, text: str) -> types.Content:
        return types.Content(
            role=role,
            parts=[types.Part.from_text(text=text)],
        )

    @staticmethod
    def _extract_text(response: Any, max_chars: int) -> str:
        text = str(response.text or "").strip()
        if not text:
            raise EmptyGeminiResponse("응답 텍스트가 비어 있습니다.")
        if len(text) > max_chars:
            return f"{text[: max_chars - 1].rstrip()}…"
        return text

    @staticmethod
    def _normalize_prompt(prompt: str) -> str:
        normalized = str(prompt).strip()
        if not normalized:
            raise ValueError("prompt는 비어 있을 수 없습니다.")
        return normalized

    @staticmethod
    def _fortune_metadata(
        *,
        metadata: dict[str, Any] | None,
        name: str,
        birthdate: str,
        question: str,
    ) -> dict[str, Any]:
        return {
            **(metadata or {}),
            "type": "fortune",
            "name": name,
            "birthdate": birthdate,
            "question": question,
        }

    @staticmethod
    def _matches_chat(
        record: dict[str, Any],
        metadata: dict[str, Any],
    ) -> bool:
        record_metadata = record.get("metadata")
        if not isinstance(record_metadata, dict):
            return False
        if record_metadata.get("type", "chat") != "chat":
            return False
        if str(record_metadata.get("user_id") or "") != str(
            metadata.get("user_id") or ""
        ):
            return False

        chat_id = metadata.get("chat_id")
        if chat_id is not None:
            return str(record_metadata.get("chat_id") or "") == str(chat_id)
        return True

    def _backup_corrupt_history(self) -> None:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_file = self.backup_dir / (
                f"{self.data_file.stem}_corrupt_{timestamp}.json"
            )
            shutil.copy2(self.data_file, backup_file)
        except OSError:
            logger.exception("Corrupt Gemini history backup failed")

    @staticmethod
    def _log_api_error(model: str, error: genai_errors.APIError) -> None:
        logger.warning(
            "Gemini API error: model=%s code=%s status=%s error=%s",
            model,
            error.code,
            error.status,
            error,
        )


gemini_bot = GeminiBot()
