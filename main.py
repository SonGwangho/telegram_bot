from telegram.ext import Application, CommandHandler, MessageHandler, filters

from commands import (
    bb_command,
    bbr_command,
    chat_command,
    dday_command,
    fortune_command,
    help_command,
    korea_stock_command,
    lck_command,
    remember_message,
    register_command,
    start_command,
    sum_command,
    urlShortening_command,
    us_stock_command,
    word_command,
)
from config import telegram_token
from gemini import gemini_bot


async def post_shutdown(_application: Application) -> None:
    await gemini_bot.close()


def main() -> None:
    application = (
        Application.builder()
        .token(telegram_token)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("dday", dday_command))
    application.add_handler(CommandHandler("reg", register_command))
    application.add_handler(CommandHandler("bb", bb_command))
    application.add_handler(CommandHandler("bbr", bbr_command))
    application.add_handler(CommandHandler("lck", lck_command))
    application.add_handler(CommandHandler("ks", korea_stock_command))
    application.add_handler(CommandHandler("us", us_stock_command))
    application.add_handler(CommandHandler("f", fortune_command))
    application.add_handler(CommandHandler("word", word_command))
    application.add_handler(CommandHandler("chat", chat_command))
    application.add_handler(CommandHandler("sum", sum_command))
    application.add_handler(CommandHandler("url", urlShortening_command))
    application.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND) | filters.CAPTION,
            remember_message,
        ),
        group=1,
    )

    application.run_polling()


if __name__ == "__main__":
    main()
