from telegram.ext import Application, CommandHandler

from commands import chat_command, fortune_command, help_command, start_command, register_command, bb_command, bbr_command, lck_command, stock_command
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
    application.add_handler(CommandHandler("reg", register_command))
    application.add_handler(CommandHandler("bb", bb_command))
    application.add_handler(CommandHandler("bbr", bbr_command))
    application.add_handler(CommandHandler("lck", lck_command))
    application.add_handler(CommandHandler("stock", stock_command))
    application.add_handler(CommandHandler("f", fortune_command))
    application.add_handler(CommandHandler("chat", chat_command))

    application.run_polling()


if __name__ == "__main__":
    main()
