from telegram import Update
from telegram.ext import ContextTypes
import requests
from bs4 import BeautifulSoup
from MyUtils import MyUtils

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("안녕하세요. 텔레그램 봇이 시작되었습니다.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "사용 가능한 명령어\n"
        "/help - 도움말 보기\n"
        "/bb - 오늘 삼성 야구함?"
    )
    await update.message.reply_text(help_text)

async def bb_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args

    


    res = requests.get("https://www.samsunglions.com/score/score_index.asp")
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    table = soup.select("#infodiv > div.mCalendar > div.result > div > div.cal > table")
    games = table[0].select("td.game")

    month = MyUtils.getMonth()
    today = MyUtils.getDay()

    # if args[0] == "내일":
    #     today += 1
    # elif args[0] == "모레":
    #     today += 2

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
        await update.message.reply_text(today_game, parse_mode="HTML")
    else:
        await update.message.reply_text("오늘 경기 없음")