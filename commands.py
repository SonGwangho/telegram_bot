import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes
from concurrent.futures import ThreadPoolExecutor

from config import admin_user_id

from MyUtils import MyUtils
from TelegramBot import TelegramBot
from datetime import datetime, timedelta
from gemini import gemini_bot
import myService
import storage

telegram_bot = TelegramBot()


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
        '/stock - 증시 정보\n'
        '/f - 오늘의 운세\n'
        '/chat 질문 - AI와 대화하기\n'
    )
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


async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    today_str = MyUtils.getToday("yyyymmdd")

    #9시인지 체크
    if MyUtils._get_datetime(fmt="%Y-%m-%d %H:%M:%S").hour < 9:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text="증시 정보는 오전 9시 이후에 제공됩니다.",
        )
        return

    codes_domestic = ["069500", "005930", "000660", "035420", "066570", "005380", "012450", "229200"]
    상미씨_대우건설 = "047040"
    codes_world_index = [".INX"]
    codes_world_stock = ["GOOG.O"]
    codes_world_etf = ["SCHD.K"]

    # 대우건설 넣기
    codes_domestic.insert(4, 상미씨_대우건설)

    results = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        domestic_results = list(executor.map(myService.fetch_domestic, codes_domestic))
        world_index_results = list(executor.map(myService.fetch_world, codes_world_index, ["index"] * len(codes_world_index)))
        world_stock_results = list(executor.map(myService.fetch_world, codes_world_stock, ["stock"] * len(codes_world_stock)))
        world_etf_results = list(executor.map(myService.fetch_world, codes_world_etf, ["etf"] * len(codes_world_etf)))

    results.extend(domestic_results)
    results.extend(world_index_results)
    results.extend(world_stock_results)
    results.extend(world_etf_results)

    usd = MyUtils.getUSD()

    return_text = f"<b>{today_str} 주식 정보</b>\n<b>환율 : {usd:,}원</b>\n\n"  
    
    for item in results:
        value = item["value"] if item["isKRW"] else item["value"] * usd
        return_text += (
            f'{item["name"]} : {value:,.0f} '
            f'({item["sign"]}{item["rate"]:.2f}%) {item["emoji"]}\n'
        )

    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text = return_text,
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
    question = " ".join(context.args).strip() if context.args else "today"
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
            parse_mode="HTML",
        )
        return

    answer = await gemini_bot.generate_fortune_async(
        name,
        birthdate,
        f"이름은 {name}이고 생일은 {birthdate}야. {today_str} 날짜 기준으로 '{question}' 질문에 맞춰 운세 알려줘.",
    )

    user_cache[cache_key] = answer
    storage.update("fortune_cache", fortune_cache)

    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text=answer,
        parse_mode="HTML",
    )

async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    
    cache = {}
    if storage.isExist("chat_cache"):
        cache = storage.get("chat_cache")
    else:
        storage.create("chat_cache")

    if not context.args:
        await telegram_bot.send_message(
            chat_id=update.effective_chat.id,
            text="질문을 입력해주세요. 예시: /chat 오늘 날씨 어때?",
            parse_mode="HTML",
        )
        return
    
    question = " ".join(context.args).strip()

    user_cache = cache.setdefault(user_id, {})
    last_chat_datetime_str = user_cache.get("last_chat_datetime")

    now_datetime = MyUtils._get_datetime(fmt="%Y-%m-%d %H:%M:%S")
    if user_id != admin_user_id and last_chat_datetime_str:

        last_chat_datetime = MyUtils._get_datetime(last_chat_datetime_str, "%Y-%m-%d %H:%M:%S")
        if now_datetime - last_chat_datetime < timedelta(minutes=1):
            await telegram_bot.send_message(
                chat_id=update.effective_chat.id,
                text="1분에 1번씩만 질문할 수 있어요",
                parse_mode="HTML",
            )
            return
    
    user_cache["last_chat_datetime"] = now_datetime.strftime("%Y-%m-%d %H:%M:%S")
    storage.update("chat_cache", cache)

    answer = await gemini_bot.generate_text_async(
        question,
    )
    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text=answer,
        parse_mode="HTML",
    )
    