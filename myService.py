from __future__ import annotations

import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Literal, TypedDict
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)

NAVER_FINANCE_URL = "https://polling.finance.naver.com/api/realtime"
NAVER_WORLD_STOCK_URL = f"{NAVER_FINANCE_URL}/worldstock"
NAVER_EXCHANGE_URL = (
    "https://m.search.naver.com/p/csearch/content/qapirender.nhn"
)
REQUEST_TIMEOUT = (3.05, 7)
RETRYABLE_STATUS_CODES = (408, 429, 500, 502, 503, 504)

StockKind = Literal["domestic", "index", "stock", "etf"]
WORLD_STOCK_KINDS = frozenset({"index", "stock", "etf"})


class StockQuote(TypedDict):
    code: str
    kind: StockKind
    isKRW: bool
    name: str
    value: float
    rate: float
    sign: str
    emoji: str


@dataclass(frozen=True, slots=True)
class StockTarget:
    code: str
    kind: StockKind
    remark: str | None = ""

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("종목 코드는 비어 있을 수 없습니다.")
        if self.kind not in {"domestic", *WORLD_STOCK_KINDS}:
            raise ValueError(f"지원하지 않는 종목 유형입니다: {self.kind}")


@dataclass(frozen=True, slots=True)
class StockFailure:
    target: StockTarget
    reason: str


class StockFetchError(RuntimeError):
    """Raised when a finance endpoint cannot return a usable value."""


_thread_local = threading.local()


def _build_session() -> requests.Session:
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.4,
        status_forcelist=RETRYABLE_STATUS_CODES,
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=8,
        pool_maxsize=8,
    )

    session = requests.Session()
    session.mount("https://", adapter)
    session.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://finance.naver.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126 Safari/537.36"
            ),
        }
    )
    return session


def _get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = _build_session()
        _thread_local.session = session
    return session


def _request_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    client = session or _get_session()

    try:
        response = client.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as error:
        raise StockFetchError("주식 정보 서버 요청에 실패했습니다.") from error

    try:
        payload = response.json()
    except (TypeError, ValueError) as error:
        raise StockFetchError("주식 정보 서버가 잘못된 JSON을 반환했습니다.") from error

    if not isinstance(payload, dict):
        raise StockFetchError("주식 정보 응답 형식이 올바르지 않습니다.")
    return payload


def _to_float(value: Any, field_name: str) -> float:
    normalized = value.replace(",", "").strip() if isinstance(value, str) else value
    try:
        number = float(normalized)
    except (TypeError, ValueError) as error:
        raise StockFetchError(f"{field_name} 값이 숫자가 아닙니다.") from error

    if not math.isfinite(number):
        raise StockFetchError(f"{field_name} 값이 유효하지 않습니다.")
    return number


def _direction(value: int) -> tuple[str, str]:
    if value > 0:
        return "+", "🔺"
    if value < 0:
        return "-", "🔻"
    return "", "-"


def fetch_domestic(
    code: str,
    *,
    session: requests.Session | None = None,
) -> StockQuote:
    code = code.strip()
    if not code:
        raise ValueError("종목 코드는 비어 있을 수 없습니다.")

    payload = _request_json(
        NAVER_FINANCE_URL,
        params={"query": f"SERVICE_ITEM:{code}"},
        session=session,
    )

    try:
        data = payload["result"]["areas"][0]["datas"][0]
        direction = 1 if str(data.get("rf")) == "2" else -1 if str(data.get("rf")) == "5" else 0
        sign, emoji = _direction(direction)
        return {
            "code": code,
            "kind": "domestic",
            "isKRW": True,
            "name": str(data.get("nm") or code),
            "value": _to_float(data["nv"], "현재가"),
            "rate": abs(_to_float(data["cr"], "등락률")),
            "sign": sign,
            "emoji": emoji,
        }
    except StockFetchError:
        raise
    except (IndexError, KeyError, TypeError) as error:
        raise StockFetchError(f"국내 종목 {code}의 응답 형식이 변경되었습니다.") from error


def fetch_world(
    code: str,
    kind: str,
    *,
    session: requests.Session | None = None,
) -> StockQuote:
    code = code.strip()
    if not code:
        raise ValueError("종목 코드는 비어 있을 수 없습니다.")
    if kind not in WORLD_STOCK_KINDS:
        raise ValueError(f"지원하지 않는 해외 종목 유형입니다: {kind}")

    safe_code = quote(code, safe="")
    payload = _request_json(
        f"{NAVER_WORLD_STOCK_URL}/{kind}/{safe_code}",
        session=session,
    )

    try:
        data = payload["datas"][0]
        comparison = data.get("compareToPreviousPrice") or {}
        status = str(comparison.get("name", "")).upper()
        direction = 1 if status == "RISING" else -1 if status == "FALLING" else 0
        sign, emoji = _direction(direction)
        name_key = "indexName" if kind == "index" else "stockName"
        return {
            "code": code,
            "kind": kind,
            "isKRW": False,
            "name": str(data.get(name_key) or code),
            "value": _to_float(data["closePriceRaw"], "현재가"),
            "rate": abs(_to_float(data["fluctuationsRatioRaw"], "등락률")),
            "sign": sign,
            "emoji": emoji,
        }
    except StockFetchError:
        raise
    except (IndexError, KeyError, TypeError) as error:
        raise StockFetchError(f"해외 종목 {code}의 응답 형식이 변경되었습니다.") from error


def fetch_usd_krw(*, session: requests.Session | None = None) -> float:
    payload = _request_json(
        NAVER_EXCHANGE_URL,
        params={
            "key": "calculator",
            "pkid": "141",
            "q": "환율",
            "where": "m",
            "u1": "keb",
            "u2": "1",
            "u3": "USD",
            "u4": "KRW",
            "u6": "standardUnit",
            "u7": "0",
            "u8": "down",
        },
        session=session,
    )

    try:
        countries = payload["country"]
        krw_data = countries[1]
        return _to_float(krw_data["value"], "USD/KRW 환율")
    except StockFetchError:
        raise
    except (IndexError, KeyError, TypeError) as error:
        raise StockFetchError("환율 응답 형식이 변경되었습니다.") from error


def _fetch_target(target: StockTarget) -> StockQuote:
    if target.kind == "domestic":
        return fetch_domestic(target.code)
    return fetch_world(target.code, target.kind)


def fetch_quotes(
    targets: list[StockTarget] | tuple[StockTarget, ...],
    *,
    max_workers: int = 8,
) -> tuple[list[StockQuote], list[StockFailure]]:
    """Fetch quotes concurrently while keeping successful results in input order."""

    if not targets:
        return [], []
    if max_workers < 1:
        raise ValueError("max_workers는 1 이상이어야 합니다.")

    quotes: dict[int, StockQuote] = {}
    failures: dict[int, StockFailure] = {}

    with ThreadPoolExecutor(max_workers=min(max_workers, len(targets))) as executor:
        futures = {
            executor.submit(_fetch_target, target): (index, target)
            for index, target in enumerate(targets)
        }
        for future in as_completed(futures):
            index, target = futures[future]
            try:
                quotes[index] = future.result()
                quotes[index]["remark"] = target.remark
            except Exception as error:
                reason = str(error) or error.__class__.__name__
                logger.warning(
                    "Stock quote fetch failed: code=%s kind=%s error=%s",
                    target.code,
                    target.kind,
                    target.remark,
                    reason,
                )
                failures[index] = StockFailure(target=target, reason=reason)

    ordered_quotes = [quotes[index] for index in sorted(quotes)]
    ordered_failures = [failures[index] for index in sorted(failures)]
    return ordered_quotes, ordered_failures
