from telegram import Update
from telegram.ext import ContextTypes


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("안녕하세요. 텔레그램 봇이 시작되었습니다.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "사용 가능한 명령어\n"
        "/help - 도움말 보기\n"
    )
    await update.message.reply_text(help_text)
