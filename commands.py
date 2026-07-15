import asyncio
import html
import logging
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes

from config import admin_user_id
from config import admin_chat_id

from MyUtils import MyUtils
from TelegramBot import TelegramBot
from gemini import gemini_bot
import myService
import storage

telegram_bot = TelegramBot()
logger = logging.getLogger(__name__)

STOCK_CACHE_KEY = "stock_snapshot"
STOCK_CACHE_SECONDS = 60
MAX_CHAT_QUESTION_LENGTH = 2_000
CHAT_RESET_WORDS = {"reset", "초기화", "대화초기화"}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text="안녕하세요. 텔레그램 봇이 시작되었습니다.",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "사용 가능한 명령어\n"
        "/help - 도움말 보기\n"
        "/reg 이름 생년월일(YYYYMMDD) - 사용자 등록\n"
        '/bb ["", "오늘", "내일", "모레"] - 삼성 야구 일정\n'
        '/bbr ["", yyyy-mm-dd] - 삼성 야구 결과\n'
        '/lck ["", "오늘", "내일", "모레"] - 롤 경기 일정\n'
        '/ks - 증시 정보\n'
        '/us - 미국 증시 정보\n'
        '/f - 오늘의 운세\n'
        '/chat 질문 - AI와 대화하기\n'
        '/chat 초기화 - 이전 AI 대화 지우기\n'
    )

    print(f"help_command called by user_id={update.effective_user.id}")
    print(f"help_command called by chat_id={update.effective_chat.id}")

    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text=help_text,
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
        datetime.strptime(birthdate, "%Y%m%d")
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
        

async def lck_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args

    res = requests.get("https://esports-api.game.naver.com/service/v1/predict/leagueId/lck_2026", timeout=10)
    res.raise_for_status()

    json = res.json()
    matches = json["content"]["matches"]

    matches = list(filter(lambda x: x["matchStatus"] != "RESULT", matches))

    year = MyUtils.getYear()
    month = MyUtils.getMonth()
    day = MyUtils.getDay()

    today = 0
    if args:
        if args[0] == "내일":
            today += 2
            day += 1
        elif args[0] == "모레":
            today += 4
            day += 2
        elif args[0].isdigit():
            today += int(args[0]) * 2
            day += int(args[0])
    

    away = [matches[today]["awayTeam"]["name"], matches[today + 1]["awayTeam"]["name"]]
    home = [matches[today]["homeTeam"]["name"], matches[today + 1]["homeTeam"]["name"]]

    return_text = f'''
<b>{year}년 {month}월 {day}일 경기</b>
1경기 {away[0]} vs {home[0]}
2경기 {away[1]} vs {home[1]}
    '''
    
    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text = return_text,
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
        myService.StockTarget("QQQ.O", "etf", "QQQ"),  # Invesco QQQ Trust
        myService.StockTarget("SCHD.K", "etf", "SCHD"),  # Schwab U.S. Dividend Equity ETF
        myService.StockTarget("JEPQ.O", "etf", "JEPQ"),
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
