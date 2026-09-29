"""짧은 조회 캐시와 동일한 외부 요청의 중복 실행을 관리한다."""

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from time import monotonic
from typing import Generic, TypeVar


T = TypeVar("T")
logger = logging.getLogger(__name__)


class AsyncTTLCache(Generic[T]):
    """하나의 봇 이벤트 루프에서 사용한다. 유효시간은 조회 완료부터 센다."""

    def __init__(self, ttl_seconds: float, *, max_entries: int = 128) -> None:
        if ttl_seconds <= 0 or max_entries < 1:
            raise ValueError("캐시 유효시간과 최대 항목 수는 양수여야 합니다.")
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: OrderedDict[Hashable, tuple[float, T]] = OrderedDict()
        self._inflight: dict[Hashable, asyncio.Task[T]] = {}

    async def get(
        self,
        key: Hashable,
        fetch: Callable[[], Awaitable[T]],
        *,
        cache_if: Callable[[T], bool] | None = None,
    ) -> T:
        entry = self._entries.get(key)
        if entry is not None:
            expires_at, value = entry
            if monotonic() < expires_at:
                self._entries.move_to_end(key)
                return value
            del self._entries[key]

        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._fetch_and_store(key, fetch, cache_if))
            self._inflight[key] = task
            task.add_done_callback(self._observe_completion)
        # 한 사용자의 요청이 취소돼도 다른 사용자가 기다리는 조회는 계속한다.
        return await asyncio.shield(task)

    async def _fetch_and_store(
        self,
        key: Hashable,
        fetch: Callable[[], Awaitable[T]],
        cache_if: Callable[[T], bool] | None,
    ) -> T:
        try:
            value = await fetch()
            if cache_if is None or cache_if(value):
                self._entries[key] = (monotonic() + self.ttl_seconds, value)
                self._entries.move_to_end(key)
                while len(self._entries) > self.max_entries:
                    self._entries.popitem(last=False)
            return value
        except Exception:
            logger.exception("External lookup failed; result was not cached.")
            raise
        finally:
            self._inflight.pop(key, None)

    @staticmethod
    def _observe_completion(task: asyncio.Task[T]) -> None:
        # 모든 대기자가 취소돼도 예외는 위에서 기록되고, 미수거 경고는 남지 않는다.
        if not task.cancelled():
            task.exception()
