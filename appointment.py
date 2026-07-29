from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

import requests


FITNESS_API_URL = "https://gwangho.vercel.app/api/fitness"
REQUEST_TIMEOUT = (3.05, 7)
SEOUL_TIMEZONE = timezone(timedelta(hours=9), name="Asia/Seoul")


@dataclass(frozen=True, slots=True)
class Appointment:
    date: date
    memo: str


class AppointmentFetchError(RuntimeError):
    """Raised when the appointment API does not return usable data."""


def seoul_today() -> date:
    return datetime.now(SEOUL_TIMEZONE).date()


def _parse_available_appointment(record: object) -> Appointment | None:
    if not isinstance(record, dict):
        return None
    if record.get("isAvailable") is not True:
        return None
    if record.get("isUnavailable") is not False:
        return None

    raw_date = record.get("date")
    raw_memo = record.get("memo")
    if not isinstance(raw_date, str) or not isinstance(raw_memo, str):
        return None

    try:
        appointment_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return None

    if appointment_date.isoformat() != raw_date:
        return None

    return Appointment(date=appointment_date, memo=raw_memo.strip())


def find_next_appointment(
    records: Iterable[object],
    *,
    today: date,
) -> Appointment | None:
    upcoming = [
        appointment
        for record in records
        if (appointment := _parse_available_appointment(record)) is not None
        and appointment.date >= today
    ]
    return min(upcoming, key=lambda appointment: appointment.date, default=None)


def fetch_next_appointment(
    *,
    today: date | None = None,
    api_url: str = FITNESS_API_URL,
    session: requests.Session | None = None,
) -> Appointment | None:
    client = session or requests

    try:
        response = client.get(api_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as error:
        raise AppointmentFetchError(
            "약속 캘린더 API 요청에 실패했습니다."
        ) from error

    try:
        payload: Any = response.json()
    except (TypeError, ValueError) as error:
        raise AppointmentFetchError(
            "약속 캘린더 API가 잘못된 JSON을 반환했습니다."
        ) from error

    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise AppointmentFetchError(
            "약속 캘린더 API 응답 형식이 올바르지 않습니다."
        )

    return find_next_appointment(
        payload["records"],
        today=today or seoul_today(),
    )


def format_dday_message(appointment: Appointment, *, today: date) -> str:
    days_until = (appointment.date - today).days
    memo = appointment.memo or "메모 없음"
    return f"{memo}\nD - {days_until}일"
