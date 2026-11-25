import asyncio
import html
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

import requests
from telegram import Message

import storage
from appointment import SEOUL_TIMEZONE
from config import attendance_api_url
from MyUtils import MyUtils
from TelegramBot import TelegramBot


telegram_bot = TelegramBot()
logger = logging.getLogger(__name__)

KeywordResponse = tuple[int | None, str | None, str]
KeywordHandler = Callable[[Message], Awaitable[None]]


KEYWORD_RESPONSES: dict[str, KeywordResponse | KeywordHandler] = {
    # "키워드": (사용자 ID, "표시 이름", "응답 문구"),
    # "키워드": (None, None, "멘션 없는 응답 문구"),
    "!명령어": handle_keyword_list,
    "!근태": handle_attendance,
    "생존신고": (5213822462, "홍 윤기", "생존신고 바람"),
    "고둥아": (None, None, "저 켜져 있어요."),
    "일정달력": (None, None, "https://gwangho.vercel.app/info/fitness?device=pc"),
    "집합": handle_mention_response,
    "메타버스": (None, None, "https://company.gwangho.party"),
    "회사": (None, None, "https://company.gwangho.party"),
    "게임": (None, None, "https://game.gwangho.party"),
}

def parse_attendance_time(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("근태 시각이 문자열이 아닙니다.")

    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=SEOUL_TIMEZONE)
    return timestamp.astimezone(SEOUL_TIMEZONE)


def find_registered_name(user_id: int) -> str:
    try:
        users = storage.get("user")
    except FileNotFoundError:
        return ""
    except (OSError, ValueError) as error:
        logger.warning("근태 사용자 이름 조회 실패 (%s)", type(error).__name__)
        return ""

    user = users.get(str(user_id)) if isinstance(users, dict) else None
    name = user.get("name") if isinstance(user, dict) else None
    return name.strip() if isinstance(name, str) else ""


def fetch_attendance_message(user_id: int) -> str:
    response = requests.get(
        attendance_api_url,
        params={"telegramUserId": user_id},
        timeout=5,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(
        members := payload.get("members"), list
    ):
        raise ValueError("근태 API 응답에 members 목록이 없습니다.")
    if not members:
        return "등록된 근태 정보가 없습니다."
    if len(members) != 1 or not isinstance(members[0], dict):
        raise ValueError("근태 API가 사용자 한 명의 정보를 반환하지 않았습니다.")

    member = members[0]
    name = find_registered_name(user_id)
    title = f"{name}님의 근태 정보" if name else "근태 정보"

    check_in = parse_attendance_time(member.get("checkedInAt"))
    check_out = parse_attendance_time(member.get("scheduledCheckOutAt"))
    check_in_text = f"{check_in:%H}시 {check_in:%M}분" if check_in else "-"
    check_out_text = f"{check_out:%H}시 {check_out:%M}분" if check_out else "-"

    remaining_text = "-"
    if check_out is not None:
        remaining = check_out - datetime.now(SEOUL_TIMEZONE)
        remaining_seconds = max(0, int(remaining.total_seconds()))
        hours, remainder = divmod(remaining_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        remaining_text = f"{minutes:02d}분 {seconds:02d}초"
        if hours:
            remaining_text = f"{hours:02d}시 {remaining_text}"

    status_label = member.get("statusLabel")
    action_label = member.get("actionLabel")
    current_status = status_label or action_label or "-"
    if status_label and action_label and status_label != action_label:
        current_status = f"{status_label} ({action_label})"

    return (
        f"{title}\n"
        f"출근: {check_in_text}\n"
        f"퇴근: {check_out_text}\n"
        f"남은 시간: {remaining_text}\n"
        f"현재 상태: {current_status}"
    )


async def handle_attendance(message: Message) -> None:
    if message.from_user is None or message.sender_chat is not None:
        return

    try:
        text = await asyncio.to_thread(fetch_attendance_message, message.from_user.id)
    except (requests.RequestException, ValueError) as error:
        logger.warning("근태 API 조회 실패 (%s)", type(error).__name__)
        text = "근태 정보를 조회하지 못했습니다."

    await telegram_bot.send_message(chat_id=message.chat_id, text=text, parse_mode=None)


async def handle_url_shortening(message: Message, text: str) -> None:
    result = await asyncio.to_thread(MyUtils.urlShortening, text)
    answer = f"{html.escape(result['title'])}\n단축 URL: {html.escape(result['url'])}"

    await telegram_bot.send_message(
        chat_id=message.chat_id,
        text=answer,
        parse_mode="HTML",
    )


def find_keyword_response(
    text: str,
) -> KeywordResponse | KeywordHandler | None:
    normalized_text = text.replace(" ", "").casefold()
    for keyword, response in KEYWORD_RESPONSES.items():
        if normalized_text == keyword.replace(" ", "").casefold():
            return response

    return None


async def handle_keyword_response(
    message: Message,
    response: KeywordResponse,
) -> None:
    user_id, display_name, response_text = response
    if user_id is None or display_name is None:
        outgoing_text = html.escape(response_text)
    else:
        mention = (
            f'<a href="tg://user?id={user_id}">{html.escape(display_name)}</a>'
        )
        outgoing_text = f"{mention}\n{html.escape(response_text)}"

    await telegram_bot.send_message(
        chat_id=message.chat_id,
        text=outgoing_text,
        parse_mode="HTML",
    )

async def handle_keyword_response(
    message: Message,
    response: KeywordResponse,
) -> None:
    user_id, display_name, response_text = response
    if user_id is None or display_name is None:
        outgoing_text = html.escape(response_text)
    else:
        mention = (
            f'<a href="tg://user?id={user_id}">{html.escape(display_name)}</a>'
        )
        outgoing_text = f"{mention}\n{html.escape(response_text)}"

    await telegram_bot.send_message(
        chat_id=message.chat_id,
        text=outgoing_text,
        parse_mode="HTML",
    )

async def handle_mention_response(message: Message) -> None:
    items: list[KeywordResponse] = [
        (1929425093, "손광호", "집합"),
        (1971370370, "김다희", "집합"),
        (5178590142, "김소영", "집합"),
        (955502560, "차명구", "집합"),
        (5129445435, "송상미", "집합"),
        (1000684581, "고소은", "집합"),
        (5213822462, "홍윤기", "집합")
    ]
    mention = ""
    for (user_id, display_name, response_text) in items:
        mention += (
            f'<a href="tg://user?id={user_id}">{html.escape(display_name)}</a>'
        )
    outgoing_text = f"{mention}\n{html.escape("모두 모여라")}"

    await telegram_bot.send_message(
        chat_id=message.chat_id,
        text=outgoing_text,
        parse_mode="HTML",
    )


async def handle_keyword_list(message: Message) -> None:
    await telegram_bot.send_message(
        chat_id=message.chat_id,
        text="\n".join(KEYWORD_RESPONSES),
        parse_mode=None,
    )



async def hijack_message(message: Message) -> None:
    text = message.text or message.caption or ""
    if text.casefold().startswith(("http://", "https://")) and len(text) > 100:
        await handle_url_shortening(message, text)
        return

    keyword_response = find_keyword_response(text)
    if callable(keyword_response):
        await keyword_response(message)
    elif keyword_response is not None:
        await handle_keyword_response(message, keyword_response)
