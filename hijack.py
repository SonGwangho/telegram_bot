import asyncio
import html

from telegram import Message

from MyUtils import MyUtils
from TelegramBot import TelegramBot


telegram_bot = TelegramBot()

KeywordResponse = tuple[int | None, str | None, str]

KEYWORD_RESPONSES: dict[str, KeywordResponse] = {
    # "키워드": (사용자 ID, "표시 이름", "응답 문구"),
    # "키워드": (None, None, "멘션 없는 응답 문구"),
    "생존신고": (5213822462, "홍 윤기", "생존신고 바람"),
    "고둥아": (None, None, "저 켜져 있어요."),
    "일정 달력": (None, None, "https://gwangho.vercel.app/info/fitness"),
    "모임 위치": (None, None, "https://naver.me/FfeOGQ1i"),
}


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
) -> KeywordResponse | None:
    normalized_text = text.casefold()
    for keyword, response in KEYWORD_RESPONSES.items():
        if normalized_text.startswith(keyword.casefold()):
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


async def hijack_message(message: Message) -> None:
    text = message.text or message.caption or ""
    normalized_text = text.casefold()
    keyword_response = find_keyword_response(text)

    if normalized_text.startswith(("http://", "https://")) and len(text) > 100:
        await handle_url_shortening(message, text)
    elif keyword_response is not None:
        await handle_keyword_response(message, keyword_response)
