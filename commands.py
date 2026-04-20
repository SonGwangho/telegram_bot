import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes
from concurrent.futures import ThreadPoolExecutor

from MyUtils import MyUtils
from TelegramBot import TelegramBot
from datetime import datetime, timedelta
import myService

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
        '/bb ["", "오늘", "내일", "모레"] - 삼성 야구 일정\n'
        '/bbr ["", yyyy-mm-dd] - 삼성 야구 결과\n'
        '/lck ["", "오늘", "내일", "모레"] - 롤 경기 일정\n'
        '/stock - 증시 정보'
    )
    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text=help_text,
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

    codes_domestic = ["005930", "000660", "005380", "047040", "012450"]
    codes_world_index = [".INX"]
    codes_world_stock = ["GOOGL.O", "GOOG.O"]

    results = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        domestic_results = list(executor.map(myService.fetch_domestic, codes_domestic))
        world_index_results = list(executor.map(myService.fetch_world_index, codes_world_index))
        world_stock_results = list(executor.map(myService.fetch_world_stock, codes_world_stock))

    results.extend(domestic_results)
    results.extend(world_index_results)
    results.extend(world_stock_results)

    return_text = f"<b>{today_str} 주식 정보</b>\n\n"
    for item in results:
        return_text += (
            f'{item["name"]} : {item["value"]:,} '
            f'({item["sign"]}{item["rate"]:.2f}%) {item["emoji"]}\n'
        )

#     codes = ["005930", "000660", "005380", "047040", "012450"]
#     names = []
#     values = []
#     rates = []
#     sign = []
#     imogi = []

#     for code in codes:
#         url = f'https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{code}'
#         res = requests.get(url, timeout=10)
#         res.raise_for_status()

#         json = res.json()
#         names.append(json["result"]["areas"][0]["datas"][0]["nm"])
#         values.append(json["result"]["areas"][0]["datas"][0]["nv"])
#         rates.append(json["result"]["areas"][0]["datas"][0]["cr"])
#         if float(json["result"]["areas"][0]["datas"][0]["cr"]) > 0:
#             sign.append("+")
#             imogi.append("🔺")
#         else:
#             sign.append("-")
#             imogi.append("🔻")
    
#     url = f"https://polling.finance.naver.com/api/realtime/worldstock/index/.INX"
#     res = requests.get(url, timeout=10)
#     res.raise_for_status()

#     json = res.json()
#     data = json["datas"][0]
    
#     names.append(data["indexName"])
#     values.append(float(data["closePriceRaw"]))
#     rates.append(float(data["fluctuationsRatioRaw"]))

#     if data["compareToPreviousPrice"]["name"] == "RISING":
#         sign.append("+")
#         imogi.append("🔺")
#     else:
#         sign.append("-")
#         imogi.append("🔻")

#     codes = ["GOOGL.O", "GOOG.O"]
#     for code in codes:
#         url = f"https://polling.finance.naver.com/api/realtime/worldstock/stock/{code}"
#         res = requests.get(url, timeout=10)
#         res.raise_for_status()

#         json = res.json()
#         data = json["datas"][0]
        
#         names.append(data["stockName"])
#         values.append(float(data["closePriceRaw"]))
#         rates.append(float(data["fluctuationsRatioRaw"]))

#         if data["compareToPreviousPrice"]["name"] == "RISING":
#             sign.append("+")
#             imogi.append("🔺")
#         else:
#             sign.append("-")
#             imogi.append("🔻")

#     return_text = f'''
# <b>{today_str} 주식 정보</b>

# '''
    
#     for i in range(len(names)):
#         return_text += f"{names[i]} : {values[i]:,} ({sign[i]}{rates[i]}%) {imogi[i]}\n"

    await telegram_bot.send_message(
        chat_id=update.effective_chat.id,
        text = return_text,
        parse_mode="HTML",
    )