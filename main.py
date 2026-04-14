from telegram.ext import Application, CommandHandler

from commands import help_command, start_command
from config import telegram_token


def main() -> None:
    application = Application.builder().token(telegram_token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    application.run_polling()


if __name__ == "__main__":
    main()
