from __future__ import annotations

import asyncio
import tempfile
import unittest
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from google.genai import errors as genai_errors

from gemini import API_ERROR_PREFIX, GeminiBot


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModels:
    def __init__(self, outcomes: list[object] | None = None) -> None:
        self.outcomes = deque(outcomes or [])
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        if not self.outcomes:
            raise AssertionError("Unexpected synchronous Gemini call")
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome  # type: ignore[return-value]


class FakeAsyncModels:
    def __init__(self, outcomes: list[object] | None = None) -> None:
        self.outcomes = deque(outcomes or [])
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        if not self.outcomes:
            raise AssertionError("Unexpected asynchronous Gemini call")
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome  # type: ignore[return-value]


class FakeAsyncClient:
    def __init__(self, outcomes: list[object] | None = None) -> None:
        self.models = FakeAsyncModels(outcomes)
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(
        self,
        *,
        sync_outcomes: list[object] | None = None,
        async_outcomes: list[object] | None = None,
    ) -> None:
        self.models = FakeModels(sync_outcomes)
        self.aio = FakeAsyncClient(async_outcomes)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def api_error(message: str) -> genai_errors.APIError:
    return genai_errors.APIError(
        503,
        {
            "error": {
                "code": 503,
                "status": "UNAVAILABLE",
                "message": message,
            }
        },
    )


class GeminiBotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_bot(
        self,
        client: FakeClient | None = None,
        *,
        max_history_records: int = 2_000,
    ) -> GeminiBot:
        return GeminiBot(
            api_key="test-key",
            model="primary-model",
            lite_model="lite-model",
            data_file=self.root / "history.json",
            backup_dir=self.root / "backups",
            client=client,
            max_history_records=max_history_records,
        )

    def test_chat_falls_back_to_lite_model_and_saves_actual_model(self) -> None:
        client = FakeClient(
            sync_outcomes=[api_error("primary failed"), FakeResponse("라이트 응답")]
        )
        bot = self.make_bot(client)

        answer = bot.generate_text(
            "질문",
            metadata={"type": "chat", "user_id": "1", "chat_id": "10"},
        )

        self.assertEqual(answer, "라이트 응답")
        self.assertEqual(
            [call["model"] for call in client.models.calls],
            ["primary-model", "lite-model"],
        )
        records = bot.load_records()
        self.assertEqual(records[0]["model"], "lite-model")

    def test_api_error_keeps_original_details_and_is_not_saved(self) -> None:
        client = FakeClient(
            sync_outcomes=[api_error("first raw error"), api_error("second raw error")]
        )
        bot = self.make_bot(client)

        answer = bot.generate_text(
            "질문",
            metadata={"type": "chat", "user_id": "1", "chat_id": "10"},
        )

        self.assertTrue(answer.startswith(API_ERROR_PREFIX))
        self.assertIn("second raw error", answer)
        self.assertTrue(bot.is_error_response(answer))
        self.assertEqual(bot.load_records(), [])

    def test_async_chat_uses_role_history_for_same_chat_only(self) -> None:
        client = FakeClient(async_outcomes=[FakeResponse("새 응답")])
        bot = self.make_bot(client)
        bot.save_record(
            prompt="이전 질문",
            response="이전 답변",
            metadata={"type": "chat", "user_id": "1", "chat_id": "10"},
        )
        bot.save_record(
            prompt="다른 방 질문",
            response="다른 방 답변",
            metadata={"type": "chat", "user_id": "1", "chat_id": "20"},
        )

        answer = asyncio.run(
            bot.generate_text_async(
                "현재 질문",
                metadata={"type": "chat", "user_id": "1", "chat_id": "10"},
            )
        )

        self.assertEqual(answer, "새 응답")
        contents = client.aio.models.calls[0]["contents"]
        self.assertEqual([content.role for content in contents], ["user", "model", "user"])
        self.assertEqual(contents[0].parts[0].text, "이전 질문")
        self.assertEqual(contents[1].parts[0].text, "이전 답변")
        self.assertEqual(contents[2].parts[0].text, "현재 질문")

    def test_clear_chat_history_only_removes_selected_conversation(self) -> None:
        bot = self.make_bot()
        for chat_id in ("10", "20"):
            bot.save_record(
                prompt=f"질문 {chat_id}",
                response="답변",
                metadata={"type": "chat", "user_id": "1", "chat_id": chat_id},
            )

        deleted = bot.clear_chat_history(
            metadata={"type": "chat", "user_id": "1", "chat_id": "10"}
        )

        self.assertEqual(deleted, 1)
        records = bot.load_records()
        self.assertEqual(records[0]["metadata"]["chat_id"], "20")

    def test_concurrent_record_saves_do_not_lose_data(self) -> None:
        bot = self.make_bot(max_history_records=100)

        def save(index: int) -> None:
            bot.save_record(
                prompt=f"질문 {index}",
                response=f"답변 {index}",
                metadata={"type": "chat", "user_id": "1", "chat_id": "10"},
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(save, range(40)))

        self.assertEqual(len(bot.load_records()), 40)

    def test_fortune_uses_lite_model(self) -> None:
        client = FakeClient(sync_outcomes=[FakeResponse("오늘의 운세")])
        bot = self.make_bot(client)

        answer = bot.generate_fortune("홍길동", "19900101", "재물운")

        self.assertEqual(answer, "오늘의 운세")
        self.assertEqual(client.models.calls[0]["model"], "lite-model")
        self.assertEqual(bot.load_records()[0]["metadata"]["type"], "fortune")


if __name__ == "__main__":
    unittest.main()
