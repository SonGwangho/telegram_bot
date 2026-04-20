from telegram.ext import Application, CommandHandler

from commands import help_command, start_command, bb_command, bbr_command, lck_command, stock_command
from config import telegram_token


def main() -> None:
    application = Application.builder().token(telegram_token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("bb", bb_command))
    application.add_handler(CommandHandler("bbr", bbr_command))
    application.add_handler(CommandHandler("lck", lck_command))
    application.add_handler(CommandHandler("stock", stock_command))

    application.run_polling()


if __name__ == "__main__":
    main()
