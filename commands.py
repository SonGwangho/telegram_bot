import asyncio
import html
import logging
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes

from appointment import (
    AppointmentFetchError,
    fetch_next_appointment,
    format_dday_message,
    seoul_today,
)
from adjustment import (
    MAX_AMOUNT as ADJ_MAX_AMOUNT,
    AdjustmentError,
    add_expense,
    calculate_settlement,
    create_room,
    delete_room,
    format_room_details,
    format_settlement,
    get_room_details,
    remove_expense,
)
from chat_history import (
    ChatHistoryError,
    MAX_MESSAGES_PER_CHAT,
    build_chat_summary_prompt,
    format_chat_summary,
    get_recent_chat_messages,
    save_update_message,
)
from config import admin_user_id
from config import admin_chat_id

from MyUtils import MyUtils
from TelegramBot import TelegramBot
from gemini import gemini_bot
import hijack
import myService
import storage
from word_recommendation import (
    WORD_CACHE_NAME,
    WORD_PROMPT_VERSION,
    append_word_recommendation,
    word_profile_fingerprint,
    word_recent_recommendations,
)

telegram_bot = TelegramBot()
logger = logging.getLogger(__name__)

STOCK_CACHE_KEY = "stock_snapshot"
STOCK_CACHE_SECONDS = 60
MAX_CHAT_QUESTION_LENGTH = 2_000
CHAT_RESET_WORDS = {"reset", "초기화", "대화초기화"}
UBER_TRACKER_URL = "https://diablo2.io/dclonetracker.php"
UBER_REGION_NAMES = {
    "Europe": "유럽",
    "Americas": "미국",
    "Asia": "한국",
}
UBER_MODE_TITLES = (
    ("래더", "RotW Softcore Ladder"),
    ("스탠", "RotW Softcore Non-Ladder"),
)
UBER_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text="안녕하세요. 텔레그램 봇이 시작되었습니다.",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "사용 가능한 명령어\n"
        "/help - 도움말 보기\n"
        "/dday - 약속 남은 날짜\n"
        "/reg 이름 생년월일(YYYYMMDD) - 사용자 등록\n"
        '/bb ["", "오늘", "내일", "모레"] - 삼성 야구 일정\n'
        '/bbr ["", yyyy-mm-dd] - 삼성 야구 결과\n'
        '/ks - 증시 정보\n'
        '/us - 미국 증시 정보\n'
        '/f - 오늘의 운세\n'
        '/word - 오늘의 맞춤 추천 문장과 명언\n'
        '/chat ["초기화", "질문"] - AI 대화 및 초기화\n'
        '/sum 숫자 - 최근 메시지를 고둥이가 요약\n'
        '/uber - 디아블로 우버 진행도\n'
        '/adj - 모임 정산 생성, 결제 등록, 마감\n'
    )

    print(f"help_command called by user_id={update.effective_user.id}")
    print(f"help_command called by chat_id={update.effective_chat.id}")

    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text=help_text,
    )


ADJ_USAGE = (
    "정산 사용법\n"
    "/adj 생성 모임명 인원수\n"
    "/adj 모임명 이름 금액 [메모]\n"
    "/adj 모임명 - 현재 내역 조회\n"
    "/adj 모임명 제거 숫자코드\n"
    "/adj 마감 모임명\n"
    "※ 입력하지 않은 사람은 미입력 인원으로 자동 계산됩니다."
)


def _strip_matching_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def _parse_adj_number(value: str, label: str) -> int:
    normalized = _strip_matching_quotes(value).replace(",", "").replace("_", "")
    if label == "금액":
        normalized = normalized.removeprefix("₩").removesuffix("원")
    if not normalized.isdecimal():
        raise AdjustmentError(f"{label}은 0 이상의 숫자로 입력해 주세요.")
    number = int(normalized)
    if label == "금액" and number > ADJ_MAX_AMOUNT:
        raise AdjustmentError(f"금액은 {ADJ_MAX_AMOUNT:,}원 이하로 입력해 주세요.")
    return number


async def adj_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    args = [_strip_matching_quotes(arg) for arg in context.args]

    try:
        if len(args) == 3 and args[0] == "생성":
            room_name = args[1]
            participant_count = _parse_adj_number(args[2], "인원수")
            create_room(
                chat_id,
                room_name,
                participant_count,
                created_by=update.effective_user.id,
            )
            await telegram_bot.send_message(
                chat_id=chat_id,
                text=(
                    f"'{room_name}' 정산을 만들었습니다. ({participant_count}명)\n"
                    f"결제 등록: /adj {room_name} 이름 금액 [메모]\n"
                    "입력하지 않은 사람은 마감할 때 미입력 인원으로 계산됩니다."
                ),
                parse_mode=None,
            )
            return

        if len(args) == 2 and args[0] == "마감":
            room_name = args[1]
            result = calculate_settlement(chat_id, room_name)

            # 결과 메시지가 전송된 뒤에만 정산 데이터를 삭제한다.
            await telegram_bot.send_message(
                chat_id=chat_id,
                text=format_settlement(result),
                parse_mode=None,
            )
            try:
                delete_room(chat_id, room_name)
            except (AdjustmentError, OSError, ValueError):
                logger.exception("Failed to clear adjustment room after closing it.")
                await telegram_bot.send_message(
                    chat_id=chat_id,
                    text="정산 결과는 전송했지만 저장 내역을 삭제하지 못했습니다.",
                    parse_mode=None,
                )
            return

        if len(args) == 1:
            details = get_room_details(chat_id, args[0])
            await telegram_bot.send_message(
                chat_id=chat_id,
                text=format_room_details(details),
                parse_mode=None,
            )
            return

        if len(args) == 3 and args[1] == "제거":
            room_name = args[0]
            entry_code = args[2]
            removed, registered, expected, total = remove_expense(
                chat_id,
                room_name,
                entry_code,
            )
            memo_suffix = f" {removed.memo}" if removed.memo else ""
            await telegram_bot.send_message(
                chat_id=chat_id,
                text=(
                    f"[{room_name}] [{removed.code}] 내역을 제거했습니다.\n"
                    f"{removed.member_name} {removed.amount:,}원{memo_suffix}\n"
                    f"결제자 {registered}/{expected}명 · 전체 {total:,}원"
                ),
                parse_mode=None,
            )
            return

        if len(args) >= 3:
            room_name, member_name, amount_text = args[:3]
            amount = _parse_adj_number(amount_text, "금액")
            memo = _strip_matching_quotes(" ".join(context.args[3:]))
            entry_code, cumulative, registered, expected, total = add_expense(
                chat_id,
                room_name,
                member_name,
                amount,
                memo,
            )
            memo_suffix = f" · {memo}" if memo else ""
            await telegram_bot.send_message(
                chat_id=chat_id,
                text=(
                    f"[{room_name}] [{entry_code}] {member_name} "
                    f"{amount:,}원 반영{memo_suffix}\n"
                    f"누적 {cumulative:,}원 · 결제자 {registered}/{expected}명 · "
                    f"전체 {total:,}원"
                ),
                parse_mode=None,
            )
            return

        await telegram_bot.send_message(
            chat_id=chat_id,
            text=ADJ_USAGE,
            parse_mode=None,
        )
    except (AdjustmentError, OSError, ValueError) as error:
        logger.warning("Adjustment command failed: %s", error)
        await telegram_bot.send_message(
            chat_id=chat_id,
            text=str(error),
            parse_mode=None,
        )


def fetch_uber_progress() -> list[tuple[str, list[tuple[str, str, str]]]]:
    response = requests.get(
        UBER_TRACKER_URL,
        headers=UBER_REQUEST_HEADERS,
        timeout=10,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    member_tables = {}
    for card in soup.select(".z-dclone-table-card"):
        heading = card.select_one("h1")
        table = card.select_one("table#memberlist")
        if heading and table:
            member_tables[heading.get_text(" ", strip=True)] = table

    progress_by_mode = []
    for mode_name, table_title in UBER_MODE_TITLES:
        table = member_tables.get(table_title)
        if table is None:
            raise ValueError(f"{mode_name} 진행도 테이블을 찾지 못했습니다.")

        progress_values = []
        for row in table.select("tbody tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 3:
                continue

            code = cells[0].find("code")
            region_text = cells[1].get_text(" ", strip=True)
            last_updated = cells[2].get_text(" ", strip=True)
            region_name = next(
                (
                    korean_name
                    for region_key, korean_name in UBER_REGION_NAMES.items()
                    if region_key in region_text
                ),
                None,
            )
            if code and region_name and last_updated:
                progress_values.append(
                    (region_name, code.get_text(strip=True), last_updated)
                )

        found_regions = {region for region, _, _ in progress_values}
        if found_regions != set(UBER_REGION_NAMES.values()):
            raise ValueError(f"{mode_name} 우버 진행도 3개를 모두 찾지 못했습니다.")

        progress_by_mode.append((mode_name, progress_values))

    return progress_by_mode


async def uber_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await telegram_bot.send_chat_action(chat_id)

    try:
        progress_by_mode = await asyncio.to_thread(fetch_uber_progress)
    except (requests.RequestException, ValueError):
        logger.warning("Failed to fetch Uber progress.", exc_info=True)
        await telegram_bot.send_message(
            chat_id=chat_id,
            text="우버 진행도를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
            parse_mode=None,
        )
        return

    progress_text = "\n\n".join(
        f"[{mode_name}]\n"
        + "\n".join(
            f"{region} - {value} ({last_updated})"
            for region, value, last_updated in progress_values
        )
        for mode_name, progress_values in progress_by_mode
    )
    await telegram_bot.send_message(
        chat_id=chat_id,
        text=f"우버 진행도\n\n{progress_text}",
        parse_mode=None,
    )


async def dday_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    today = seoul_today()

    await telegram_bot.send_chat_action(chat_id)

    try:
        appointment = await asyncio.to_thread(
            fetch_next_appointment,
            today=today,
        )
    except AppointmentFetchError:
        logger.warning("Failed to fetch the next appointment.", exc_info=True)
        await telegram_bot.send_message(
            chat_id=chat_id,
            text="약속 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
            parse_mode=None,
        )
        return

    if appointment is None:
        await telegram_bot.send_message(
            chat_id=chat_id,
            text="오늘 이후 등록된 약속이 없습니다.",
            parse_mode=None,
        )
        return

    await telegram_bot.send_message(
        chat_id=chat_id,
        text=format_dday_message(appointment, today=today),
        parse_mode=None,
    )


async def remember_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    try:
        await asyncio.to_thread(save_update_message, update)
    except ChatHistoryError:
        logger.exception("Failed to save a Telegram chat message.")


async def hijack_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    del context

    message = update.effective_message
    if message is None:
        return

    await hijack.hijack_message(message)


async def sum_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if len(context.args) != 1:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"사용법: /sum 숫자 (1~{MAX_MESSAGES_PER_CHAT})",
            parse_mode=None,
        )
        return

    try:
        requested_count = int(context.args[0])
    except ValueError:
        requested_count = 0

    if requested_count < 1 or requested_count > MAX_MESSAGES_PER_CHAT:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"숫자는 1부터 {MAX_MESSAGES_PER_CHAT} 사이로 입력해 주세요.",
            parse_mode=None,
        )
        return

    try:
        messages = await asyncio.to_thread(
            get_recent_chat_messages,
            update.effective_chat.id,
            limit=requested_count,
        )
    except ChatHistoryError:
        logger.exception("Failed to load Telegram chat history.")
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text="채팅 기록을 불러오지 못했습니다.",
            parse_mode=None,
        )
        return

    if not messages:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text="요약할 저장된 채팅이 없습니다.",
            parse_mode=None,
        )
        return

    await telegram_bot.send_chat_action(update.effective_chat.id)
    summary = await gemini_bot.generate_text_async(
        build_chat_summary_prompt(messages),
        model_type=gemini_bot.lite_model,
        save=False,
        metadata={
            "type": "chat_summary",
            "chat_id": str(update.effective_chat.id),
            "message_count": len(messages),
        },
        history_limit=0,
    )

    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text=format_chat_summary(
            summary,
            is_error_response=gemini_bot.is_error_response(summary),
        ),
        parse_mode=None,
    )


async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    args = context.args

    if len(args) < 2:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text="사용자 등록 형식이 올바르지 않습니다. /reg 이름 생년월일(YYYYMMDD)",
            parse_mode="HTML",
        )
        return

    name = args[0]
    birthdate = args[1]
    try:
        parsed_birthdate = datetime.strptime(birthdate, "%Y%m%d")
        if parsed_birthdate.strftime("%Y%m%d") != birthdate:
            raise ValueError
    except ValueError:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text="생년월일은 실제 날짜를 YYYYMMDD 형식으로 입력해 주세요.",
        )
        return

    user_data = {}
    if storage.isExist("user"):
        user_data = storage.get("user")
    else:
        storage.create("user")
    
    user_data[user_id] = {
        "name": name,
        "birthdate": birthdate,
    }

    storage.update("user", user_data)

    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"{name}님이 등록되었습니다.",
        parse_mode="HTML",
    )

async def bb_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args

    res = requests.get("https://www.samsunglions.com/score/score_index.asp", timeout=10)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    table = soup.select("#infodiv > div.mCalendar > div.result > div > div.cal > table")
    games = table[0].select("td.game")

    month = MyUtils.getMonth()
    today = MyUtils.getDay()
    if args:
        if args[0] == "내일":
            today += 1
        elif args[0] == "모레":
            today += 2

    today_game = None

    for game in games:
        em = game.select_one("em.d")
        day = em.contents[0].strip()

        if day == str(today):
            imgs = game.select("span.i img")
            team1 = imgs[0]["alt"]
            team2 = imgs[1]["alt"]

            info = game.select_one("span.s").get_text(strip=True)
            today_game = f"""
<b>{month}월 {day}일 경기</b>
{team1} vs {team2}
<b>{info}</b>
"""
            break

    if today_game:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text=today_game,
            parse_mode="HTML",
        )
    else:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text="경기가 없습니다.",
        )

async def bbr_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args

    params = {
        "upperCategoryId": "kbaseball",
        "categoryIds": ",kbo,kbs,kbaseballetc,premier12,apbc",
        "date": MyUtils.getToday(),
    }

    target_date = args[0] if args else MyUtils.getYesterday("%Y-%m-%d")

    res = requests.get("https://api-gw.sports.naver.com/schedule/calendar", params=params, timeout=10)
    res.raise_for_status()

    json = res.json()
    data = json["result"]

    matches = data["dates"]

    game_id = None
    game_infos = None
    for m in matches:
        if m["ymd"] == target_date:
            game_infos = m["gameInfos"]
            break

    if not game_infos:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text="경기가 없습니다.",
        )

    for g in game_infos:
        if g["homeTeamCode"] == "SS" or g["awayTeamCode"] == "SS":
            game_id = g["gameId"]
            break

    if not game_id:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text="경기가 없습니다.",
        )

    info_url = f"https://api-gw.sports.naver.com/common-poll/question/game/{game_id}/info"
    res = requests.get(info_url)

    json = res.json()
    data = json["result"]
    game_info = data["gameInfo"]

    homeTeamName = game_info["homeTeamName"]
    awayTeamName = game_info["awayTeamName"]

    homeTeamScore = game_info["homeTeamScore"]
    awayTeamScore = game_info["awayTeamScore"]
    
    game_result = f'''
<b>{target_date}</b>
{homeTeamName} {homeTeamScore} : {awayTeamScore} {awayTeamName}
'''

    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text=game_result,
        parse_mode="HTML",
    )
        

async def korea_stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    STOCK_TARGETS = (
        myService.StockTarget("005930", "domestic"),  # 삼성전자
        myService.StockTarget("000660", "domestic"),  # SK하이닉스
        myService.StockTarget("042700", "domestic"),  # 한미반도체
        myService.StockTarget("005380", "domestic"),  # 현대차
        myService.StockTarget("010120", "domestic"),  # LS ELECTRIC
        myService.StockTarget("066570", "domestic"),  # LG전자
        myService.StockTarget("069500", "domestic"),  # KODEX 200
    )
    await stock_command(update, context, "kr", STOCK_TARGETS)

async def us_stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    STOCK_TARGETS = (
        myService.StockTarget(".INX", "index", "S&P 500"),       # S&P 500
        myService.StockTarget("GOOG.O", "stock", "알파벳 C"),     # 알파벳 C
        # myService.StockTarget("MSFT.O", "stock", "마이크로소프트"),     # 마이크로소프트
        myService.StockTarget("QQQ.O", "etf", "QQQ"),  # Invesco QQQ Trust
        myService.StockTarget("SCHD.K", "etf", "SCHD"),  # Schwab U.S. Dividend Equity ETF
        myService.StockTarget("JEPQ.O", "etf", "JEPQ"),
        myService.StockTarget("VOO", "etf", "VOO"),
    )
    await stock_command(update, context, "us", STOCK_TARGETS)

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE, stock_cache_key: str, stock_targets: list[myService.StockTarget] | None = None) -> None:
    now = datetime.now()
    snapshot = context.bot_data.get(stock_cache_key + STOCK_CACHE_KEY)
    cache_is_fresh = (
        isinstance(snapshot, dict)
        and isinstance(snapshot.get("fetched_at"), datetime)
        and (now - snapshot["fetched_at"]).total_seconds() < STOCK_CACHE_SECONDS
    )

    if cache_is_fresh:
        quotes = snapshot["quotes"]
        failures = snapshot["failures"]
        usd_krw = snapshot["usd_krw"]
        fetched_at = snapshot["fetched_at"]
    else:
        await telegram_bot.send_chat_action(update.effective_chat.id)
        quote_result, exchange_result = await asyncio.gather(
            asyncio.to_thread(myService.fetch_quotes, stock_targets),
            asyncio.to_thread(myService.fetch_usd_krw),
            return_exceptions=True,
        )

        if isinstance(quote_result, Exception):
            logger.error("Stock snapshot fetch failed: %s", quote_result)
            await telegram_bot.send_message(
                chat_id=update.effective_chat.id,
                text="주식 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
            )
            return

        quotes, failures = quote_result
        if not quotes:
            failed_codes = ", ".join(failure.target.code for failure in failures)
            await telegram_bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"주식 정보를 불러오지 못했습니다. ({failed_codes})",
            )
            return

        if isinstance(exchange_result, Exception):
            logger.warning("USD/KRW fetch failed: %s", exchange_result)
            usd_krw = None
        else:
            usd_krw = exchange_result

        fetched_at = now
        context.bot_data[STOCK_CACHE_KEY] = {
            "quotes": quotes,
            "failures": failures,
            "usd_krw": usd_krw,
            "fetched_at": fetched_at,
        }

    if usd_krw is None:
        exchange_line = "환율 조회 실패 · 해외 종목은 달러로 표시"
    else:
        exchange_line = f"USD/KRW {usd_krw:,.2f}원"

    lines = [
        f"<b>{MyUtils.getToday('yyyy-mm-dd')} 주식 정보</b>",
        f"조회 {fetched_at:%H:%M:%S} · {exchange_line}",
        "",
    ]

    for quote in quotes:
        name = html.escape(str(quote["name"]))
        change = f'{quote["sign"]}{quote["rate"]:.2f}%'
        if quote["isKRW"]:
            price = f'{quote["value"]:,.0f}원'
        elif usd_krw is None:
            price = f'${quote["value"]:,.2f}'
        else:
            converted_price = quote["value"] * usd_krw
            price = f'${quote["value"]:,.2f} (약 {converted_price:,.0f}원)'

        lines.append(f'{quote["remark"] if len(quote["remark"]) > 0 else name} : {price} ({change}) {quote["emoji"]}')

    if failures:
        failed_codes = ", ".join(
            html.escape(failure.target.code) for failure in failures
        )
        lines.extend(["", f"<i>일부 종목 조회 실패: {failed_codes}</i>"])

    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text="\n".join(lines),
        parse_mode="HTML",
    )


async def word_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)
    today = MyUtils.getToday("yyyy-mm-dd")

    if storage.isExist("user"):
        user_data = storage.get("user")
    else:
        user_data = storage.create("user")

    user = user_data.get(user_id) if isinstance(user_data, dict) else None
    name = str(user.get("name") or "").strip() if isinstance(user, dict) else ""
    birthdate = (
        str(user.get("birthdate") or "").strip()
        if isinstance(user, dict)
        else ""
    )
    if not name or not birthdate:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text="사용자 등록을 먼저 해주세요 /reg 이름 생년월일(YYYYMMDD)",
            parse_mode=None,
        )
        return

    try:
        parsed_birthdate = datetime.strptime(birthdate, "%Y%m%d")
        if parsed_birthdate.strftime("%Y%m%d") != birthdate:
            raise ValueError
    except ValueError:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text="사용자 정보를 다시 등록해 주세요 /reg 이름 생년월일(YYYYMMDD)",
            parse_mode=None,
        )
        return

    profile_fingerprint = word_profile_fingerprint(name, birthdate)

    if storage.isExist(WORD_CACHE_NAME):
        word_cache = storage.get(WORD_CACHE_NAME)
    else:
        word_cache = storage.create(WORD_CACHE_NAME)

    if not isinstance(word_cache, dict):
        word_cache = {}

    cached_entry = word_cache.get(user_id)
    recent_recommendations = word_recent_recommendations(
        cached_entry,
        profile_fingerprint,
    )
    cache_is_current = (
        isinstance(cached_entry, dict)
        and cached_entry.get("date") == today
        and cached_entry.get("profile_fingerprint") == profile_fingerprint
        and cached_entry.get("prompt_version") == WORD_PROMPT_VERSION
    )
    if cache_is_current:
        cached_answer = cached_entry.get("answer")
        if isinstance(cached_answer, str) and cached_answer.strip():
            await telegram_bot.send_message(
                chat_id=update.effective_chat.id,
                text=cached_answer,
                parse_mode=None,
            )
            return

    await telegram_bot.send_chat_action(update.effective_chat.id)
    answer = await gemini_bot.generate_daily_recommendation_async(
        name=name,
        birthdate=birthdate,
        date=today,
        recent_recommendations=recent_recommendations,
        metadata={
            "user_id": user_id,
            "chat_id": chat_id,
        },
        save=False,
    )

    if not gemini_bot.is_error_response(answer):
        word_cache[user_id] = {
            "date": today,
            "profile_fingerprint": profile_fingerprint,
            "prompt_version": WORD_PROMPT_VERSION,
            "answer": answer,
            "recent_recommendations": append_word_recommendation(
                recent_recommendations,
                answer,
            ),
        }
        storage.update(WORD_CACHE_NAME, word_cache)

    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text=answer,
        parse_mode=None,
    )


async def fortune_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)

    user_json = {}
    if storage.isExist("user"):
        user_json = storage.get("user")
    else:
        storage.create("user")
    
    user = user_json.get(user_id)

    if not user:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text = "사용자 등록을 먼저 해주세요 /reg 이름 생년월일(YYYYMMDD)",
            parse_mode="HTML",
        )
        return

    name = user["name"]
    birthdate = user["birthdate"]

    today_str = MyUtils.getToday("yyyy-mm-dd")
    question = " ".join(context.args).strip() if context.args else "오늘의 종합 운세"
    cache_key = f"{today_str}:{question}"

    fortune_cache = {}
    if storage.isExist("fortune_cache"):
        fortune_cache = storage.get("fortune_cache")
    else:
        storage.create("fortune_cache")

    user_cache = fortune_cache.setdefault(user_id, {})
    cached_answer = user_cache.get(cache_key)

    if cached_answer:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text=cached_answer,
        )
        return

    await telegram_bot.send_chat_action(update.effective_chat.id)
    answer = await gemini_bot.generate_fortune_async(
        name,
        birthdate,
        f"'{question}'에 해당하는 운세 알려줘.",
        metadata={
            "user_id": user_id,
            "chat_id": str(update.effective_chat.id),
        },
    )

    if not gemini_bot.is_error_response(answer):
        user_cache[cache_key] = answer
        storage.update("fortune_cache", fortune_cache)

    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text=answer,
    )

async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)

    user_json = {}
    if storage.isExist("user"):
        user_json = storage.get("user")
    else:
        storage.create("user")
    
    user = user_json.get(user_id)

    if not user:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text = "사용자 등록을 먼저 해주세요 /reg 이름 생년월일(YYYYMMDD)",
            parse_mode="HTML",
        )
        return
    
    if not context.args:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text="질문을 입력해주세요. 예시: /chat 오늘 날씨 어때?",
        )
        return
    
    question = " ".join(context.args).strip()
    if len(question) > MAX_CHAT_QUESTION_LENGTH:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"질문은 {MAX_CHAT_QUESTION_LENGTH:,}자 이내로 입력해 주세요.",
        )
        return

    metadata = {
        "type": "chat",
        "user_id": user_id,
        "chat_id": chat_id,
    }
    if question.casefold() in CHAT_RESET_WORDS:
        deleted_count = await asyncio.to_thread(
            gemini_bot.clear_chat_history,
            metadata=metadata,
        )
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"이전 AI 대화 {deleted_count}개를 지웠습니다.",
        )
        return

    cache = {}
    if storage.isExist("chat_cache"):
        cache = storage.get("chat_cache")
    else:
        storage.create("chat_cache")

    user_cache = cache.setdefault(user_id, {})
    last_chat_datetime_str = user_cache.get("last_chat_datetime")

    now_datetime = MyUtils._get_datetime(fmt="%Y-%m-%d %H:%M:%S")
    if user_id != admin_user_id and admin_chat_id != chat_id and last_chat_datetime_str:

        last_chat_datetime = MyUtils._get_datetime(last_chat_datetime_str, "%Y-%m-%d %H:%M:%S")
        if now_datetime - last_chat_datetime < timedelta(minutes=1):
            await telegram_bot.send_message(
                chat_id=update.effective_chat.id,
                text="1분에 1번씩만 질문할 수 있어요",
            )
            return
    
    user_cache["last_chat_datetime"] = now_datetime.strftime("%Y-%m-%d %H:%M:%S")
    storage.update("chat_cache", cache)

    await telegram_bot.send_chat_action(update.effective_chat.id)
    answer = await gemini_bot.generate_text_async(question, metadata=metadata)
    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text=answer,
    )

async def urlShortening_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_bot.send_chat_action(update.effective_chat.id)

    url = context.args[0]
    result = MyUtils.urlShortening(url)

    answer = f"{result['title']}\n단축 URL: {result['url']}"

    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text=(answer),
    )
