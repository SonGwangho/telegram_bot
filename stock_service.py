"""주식 조회 결과를 시장·종목 목록별로 재사용하고, 환율 조회를 공유한다."""

import asyncio
from dataclasses import dataclass
from datetime import datetime

import myService
from lookup_cache import AsyncTTLCache


@dataclass(frozen=True)
class StockSnapshot:
    quotes: list[myService.StockQuote]
    failures: list[myService.StockFailure]
    usd_krw: float | None
    fetched_at: datetime


_snapshot_cache: AsyncTTLCache[StockSnapshot] = AsyncTTLCache(60, max_entries=16)
_exchange_cache: AsyncTTLCache[float] = AsyncTTLCache(60, max_entries=1)


async def get_snapshot(
    market: str,
    targets: list[myService.StockTarget] | tuple[myService.StockTarget, ...] | None,
) -> StockSnapshot:
    targets = tuple(targets or ())
    return await _snapshot_cache.get(
        (market, targets),
        lambda: _fetch_snapshot(targets),
        # 일부 실패한 결과도 보여주되 다음 요청에서 다시 조회한다.
        cache_if=lambda result: not result.failures and result.usd_krw is not None,
    )


async def _fetch_snapshot(targets: tuple[myService.StockTarget, ...]) -> StockSnapshot:
    quote_result, exchange_result = await asyncio.gather(
        asyncio.to_thread(myService.fetch_quotes, targets),
        _exchange_cache.get("USD/KRW", lambda: asyncio.to_thread(myService.fetch_usd_krw)),
        return_exceptions=True,
    )
    if isinstance(quote_result, Exception):
        raise myService.StockFetchError(
            "주식 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."
        ) from quote_result
    quotes, failures = quote_result
    if not quotes:
        failed_codes = ", ".join(failure.target.code for failure in failures)
        raise myService.StockFetchError(f"주식 정보를 불러오지 못했습니다. ({failed_codes})")

    return StockSnapshot(
        quotes=quotes,
        failures=failures,
        usd_krw=None if isinstance(exchange_result, Exception) else exchange_result,
        fetched_at=datetime.now(),
    )
