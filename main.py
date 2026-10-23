import asyncio
import logging
import sqlite3

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from commands import (
    adj_command,
    bb_command,
    bbr_command,
    chat_command,
    dday_command,
    fortune_command,
    help_command,
    hijack_command,
    korea_stock_command,
    r_command,
    remember_message,
    register_command,
    restart_command,
    start_command,
    sum_command,
    uber_command,
    us_stock_command,
    word_command,
)
from config import start_chat_id, stop_chat_id, telegram_token
from gemini import gemini_bot
from reminder import ReminderService, SERVICE_KEY
from service_restart import ServiceRestartError, ensure_restart_task
from update_processor import OrderedUpdateProcessor


async def post_init(application: Application) -> None:
    reminder_service = ReminderService(application.bot)
    try:
        await reminder_service.start()
    except (OSError, sqlite3.Error):
        logging.getLogger(__name__).exception("Failed to start reminder service.")
    else:
        application.bot_data[SERVICE_KEY] = reminder_service
    try:
        await asyncio.to_thread(ensure_restart_task)
    except ServiceRestartError:
        logging.getLogger(__name__).exception("Automatic service restart setup failed.")
    await application.bot.send_message(
        chat_id=start_chat_id,
        text="고둥이가 깨어났어요! 오늘도 잘 부탁해요.",
    )


async def post_stop(application: Application) -> None:
    reminder_service = application.bot_data.get(SERVICE_KEY)
    if reminder_service is not None:
        await reminder_service.stop()
    await application.bot.send_message(
        chat_id=stop_chat_id,
        text="고둥이는 이만 쉬러 갈게요. 다음에 또 만나요.",
    )


async def post_shutdown(_application: Application) -> None:
    reminder_service = _application.bot_data.get(SERVICE_KEY)
    if reminder_service is not None:
        await reminder_service.stop()
    await gemini_bot.close()


def main() -> None:
    application = (
        Application.builder()
        .token(telegram_token)
        .concurrent_updates(OrderedUpdateProcessor())
        .post_init(post_init)
        .post_stop(post_stop)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("r", r_command))
    application.add_handler(CommandHandler("restart", restart_command))
    application.add_handler(CommandHandler("dday", dday_command))
    application.add_handler(CommandHandler("reg", register_command))
    application.add_handler(CommandHandler("bb", bb_command))
    application.add_handler(CommandHandler("bbr", bbr_command))
    application.add_handler(CommandHandler("ks", korea_stock_command))
    application.add_handler(CommandHandler("us", us_stock_command))
    application.add_handler(CommandHandler("f", fortune_command))
    application.add_handler(CommandHandler("word", word_command))
    application.add_handler(CommandHandler("chat", chat_command))
    application.add_handler(CommandHandler("sum", sum_command))
    application.add_handler(CommandHandler("uber", uber_command))
    application.add_handler(CommandHandler("adj", adj_command))
    application.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND) | filters.CAPTION,
            hijack_command,
        ),
        group=2,
    )

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
