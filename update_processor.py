"""서로 독립적인 요청은 병렬로, 같은 방이나 사용자의 요청은 순서대로 처리한다."""

import asyncio
import inspect
from collections.abc import Awaitable
from typing import Any

from telegram import Update
from telegram.ext import BaseUpdateProcessor


class OrderedUpdateProcessor(BaseUpdateProcessor):
    """실행 중이거나 순서를 기다리는 요청을 합쳐 최대 8개까지 받는다."""

    def __init__(self, max_concurrent_updates: int = 8) -> None:
        super().__init__(max_concurrent_updates)
        self._condition = asyncio.Condition()
        self._pending: dict[object, set[tuple[str, int]]] = {}
        self._active_keys: set[tuple[str, int]] = set()

    async def initialize(self) -> None:
        """외부 자원 없이 시작한다."""

    async def shutdown(self) -> None:
        """Application.stop()이 진행 중인 요청을 모두 마친 후 호출한다."""

    async def do_process_update(
        self, update: object, coroutine: Awaitable[Any]
    ) -> None:
        keys = self._ordering_keys(update)
        ticket = object()
        admitted = False
        started = False
        try:
            async with self._condition:
                self._pending[ticket] = keys
                await self._condition.wait_for(lambda: self._can_start(ticket, keys))
                del self._pending[ticket]
                self._active_keys.update(keys)
                admitted = True

            started = True
            await coroutine
        finally:
            async with self._condition:
                self._pending.pop(ticket, None)
                if admitted:
                    self._active_keys.difference_update(keys)
                self._condition.notify_all()
            if not started and inspect.iscoroutine(coroutine):
                coroutine.close()

    def _can_start(self, ticket: object, keys: set[tuple[str, int]]) -> bool:
        if keys & self._active_keys:
            return False
        for queued_ticket, queued_keys in self._pending.items():
            if queued_ticket is ticket:
                return True
            # 먼저 들어온 /reg 등이 다른 방에서 기다려도 뒤의 /f가 추월하지 않는다.
            if keys & queued_keys:
                return False
        return False

    @staticmethod
    def _ordering_keys(update: object) -> set[tuple[str, int]]:
        keys = set()
        if isinstance(update, Update):
            if update.effective_chat is not None:
                keys.add(("chat", update.effective_chat.id))
            if update.effective_user is not None:
                keys.add(("user", update.effective_user.id))
        return keys or {("unknown", 0)}
