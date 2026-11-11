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
    "일정달력": (None, None, "https://gwangho.vercel.app/info/fitness?device=pc"),
    "집합": (None, None, "집합"),
    "라운지": (None, None, "손 - https://gwangho.vercel.app/lounge\n송 - https://ssong.tail84ed05.ts.net/"),
    "내식단": (None, None, "아침 - 그릭요거트, 계란 2개\n점심 - 프로틴\n간식 - 두유, 아몬드\n저녁 - 고구마, 닭가슴살, 샐러드"),
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

async def handle_mention_response(
    message: Message,
    response: list[KeywordResponse],
) -> None:
    mention = ""
    for (user_id, display_name, response_text) in response:
        mention += (
            f'<a href="tg://user?id={user_id}">{html.escape(display_name)}</a>'
        )
    outgoing_text = f"{mention}\n{html.escape("모두 모여라")}"

    await telegram_bot.send_message(
        chat_id=message.chat_id,
        text=outgoing_text,
        parse_mode="HTML",
    )

async def hijack_message(message: Message) -> None:
    text = message.text or message.caption or ""
    normalized_text = text.replace(" ", "").casefold()
    keyword_response = find_keyword_response(text)

    if normalized_text == "집합":
        items: list[KeywordResponse] = [
            (1929425093, "손광호", "집합"),
            (1971370370, "김다희", "집합"),
            (5178590142, "김소영", "집합"),
            (955502560, "차명구", "집합"),
            (5129445435, "송상미", "집합"),
            (1000684581, "고소은", "집합"),
            (5213822462, "홍윤기", "집합")
        ]
        await handle_mention_response(message, items)
    elif text.casefold().startswith(("http://", "https://")) and len(text) > 100:
        await handle_url_shortening(message, text)
    elif keyword_response is not None:
        await handle_keyword_response(message, keyword_response)
