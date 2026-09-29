"""야구 조회, 파싱, 오류 처리를 담당한다. 공개 함수는 비동기로 호출한다."""

import asyncio
import html
import logging
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

from appointment import seoul_today
from lookup_cache import AsyncTTLCache


logger = logging.getLogger(__name__)

SCHEDULE_URL = "https://www.samsunglions.com/score/score_index.asp"
CALENDAR_URL = "https://api-gw.sports.naver.com/schedule/calendar"
GAME_INFO_URL = "https://api-gw.sports.naver.com/common-poll/question/game/{game_id}/info"
REQUEST_TIMEOUT = (3.05, 10)
NO_GAME_MESSAGE = "경기가 없습니다."
FETCH_ERRORS = (requests.RequestException, KeyError, IndexError, TypeError, ValueError)
_schedule_cache: AsyncTTLCache[str] = AsyncTTLCache(60)
_result_cache: AsyncTTLCache[str] = AsyncTTLCache(30)


async def get_schedule_message(day: str = "오늘") -> str:
    today = seoul_today()
    day = day if day in {"내일", "모레"} else "오늘"
    try:
        return await _schedule_cache.get(
            (today, day),
            lambda: asyncio.to_thread(_fetch_schedule_message, day, today=today),
        )
    except FETCH_ERRORS:
        logger.exception("Failed to fetch baseball schedule.")
        return "야구 일정을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."


async def get_result_message(target_date: str = "") -> str:
    today = seoul_today()
    target_date = target_date or (today - timedelta(days=1)).isoformat()
    try:
        return await _result_cache.get(
            (today, target_date),
            lambda: asyncio.to_thread(_fetch_result_message, target_date, today=today),
        )
    except FETCH_ERRORS:
        logger.exception("Failed to fetch baseball result.")
        return "야구 결과를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."


def _fetch_schedule_message(day: str, *, today: date | None = None) -> str:
    today = today or seoul_today()
    target_day = today.day + {"내일": 1, "모레": 2}.get(day, 0)

    with requests.get(SCHEDULE_URL, timeout=REQUEST_TIMEOUT) as response:
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

    table = soup.select_one(
        "#infodiv > div.mCalendar > div.result > div > div.cal > table"
    )
    if table is None:
        raise ValueError("Baseball schedule table is missing.")

    for game in table.select("td.game"):
        date_label = game.select_one("em.d")
        if date_label is None:
            raise ValueError("Baseball schedule date is missing.")
        game_day = str(date_label.contents[0]).strip()
        if game_day != str(target_day):
            continue

        images = game.select("span.i img")
        team1 = html.escape(images[0]["alt"])
        team2 = html.escape(images[1]["alt"])
        status = game.select_one("span.s")
        if status is None:
            raise ValueError("Baseball schedule status is missing.")
        info = html.escape(status.get_text(strip=True))
        return (
            f"\n<b>{today.month}월 {game_day}일 경기</b>\n"
            f"{team1} vs {team2}\n<b>{info}</b>\n"
        )

    return NO_GAME_MESSAGE


def _fetch_result_message(target_date: str, *, today: date | None = None) -> str:
    today = today or seoul_today()
    target_date = target_date or (today - timedelta(days=1)).isoformat()
    params = {
        "upperCategoryId": "kbaseball",
        "categoryIds": ",kbo,kbs,kbaseballetc,premier12,apbc",
        "date": today.isoformat(),
    }

    with requests.Session() as session:
        with session.get(
            CALENDAR_URL, params=params, timeout=REQUEST_TIMEOUT
        ) as response:
            response.raise_for_status()
            matches = response.json()["result"]["dates"]

        game_infos = None
        for match in matches:
            if match["ymd"] == target_date:
                game_infos = match["gameInfos"]
                break
        if not game_infos:
            return NO_GAME_MESSAGE

        game_id = None
        for game in game_infos:
            if game["homeTeamCode"] == "SS" or game["awayTeamCode"] == "SS":
                game_id = game["gameId"]
                break
        if not game_id:
            return NO_GAME_MESSAGE

        with session.get(
            GAME_INFO_URL.format(game_id=game_id), timeout=REQUEST_TIMEOUT
        ) as response:
            response.raise_for_status()
            game_info = response.json()["result"]["gameInfo"]

    home_team = html.escape(str(game_info["homeTeamName"]))
    away_team = html.escape(str(game_info["awayTeamName"]))
    home_score = html.escape(str(game_info["homeTeamScore"]))
    away_score = html.escape(str(game_info["awayTeamScore"]))
    return (
        f"\n<b>{html.escape(target_date)}</b>\n"
        f"{home_team} {home_score} : {away_score} {away_team}\n"
    )
