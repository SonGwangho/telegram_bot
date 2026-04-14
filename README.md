# Telegram Bot

텔레그램 챗봇 프로젝트 기본 사용 방법입니다.

## 설치
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 실행
```powershell
python main.py
```

## 1. `main.py`에서 `commands.py` 함수 가져와서 이벤트 등록하는 법

`commands.py`에는 `/start`, `/help` 같은 명령어 처리 함수를 만들고, 등록은 `main.py`에서 합니다.

예시:

```python
from telegram.ext import Application, CommandHandler

from config import telegram_token
from commands import start_command, help_command


def main():
    app = Application.builder().token(telegram_token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    app.run_polling()


if __name__ == "__main__":
    main()
```

설명:
- `CommandHandler("start", start_command)`은 `/start` 명령어가 들어오면 `start_command` 함수를 실행합니다.
- 명령어 함수는 `commands.py`에 두고, 봇 실행과 핸들러 등록은 `main.py`에서 담당합니다.

## 2. `TelegramBot.py` 클래스 사용하는 법

`TelegramBot` 클래스는 Bot API를 직접 호출할 때 사용하는 공통 유틸 클래스입니다.
명령어 핸들러와 별개로, 원하는 채팅방에 메시지를 보내거나 이미지, 파일을 보내는 데 사용할 수 있습니다.

기본 사용 예시:

```python
import asyncio

from TelegramBot import TelegramBot


async def main():
    bot = TelegramBot()

    await bot.send_message(
        chat_id=123456789,
        text="안녕하세요. 테스트 메시지입니다."
    )

    await bot.send_photo(
        chat_id=123456789,
        photo="sample.jpg",
        caption="테스트 이미지"
    )

    await bot.send_document(
        chat_id=123456789,
        document="guide.pdf",
        caption="테스트 문서"
    )

    await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
```

주요 메서드:
- `send_message(chat_id, text)`
- `reply_message(chat_id, message_id, text)`
- `send_photo(chat_id, photo, caption=None)`
- `send_document(chat_id, document, caption=None)`
- `send_audio(chat_id, audio, caption=None)`
- `send_video(chat_id, video, caption=None)`
- `send_media_group(chat_id, media_items)`
- `send_chat_action(chat_id, action)`
- `edit_message_text(chat_id, message_id, text)`
- `delete_message(chat_id, message_id)`

참고:
- 토큰은 `config.py`의 `telegram_token`을 자동으로 사용합니다.
- 이 클래스의 메서드는 `async`이므로 `await`로 호출해야 합니다.

## 3. `commands.py`에서 이벤트 함수 만드는 법

명령어 함수는 보통 아래 형태로 만듭니다.

```python
from telegram import Update
from telegram.ext import ContextTypes


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("안녕하세요. 봇이 시작되었습니다.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "/start - 봇 시작\n"
        "/help - 도움말 보기"
    )
    await update.message.reply_text(help_text)
```

구조 설명:
- `update`: 사용자가 보낸 메시지, 채팅 정보, 유저 정보가 들어 있습니다.
- `context`: 봇 상태, 인자, 추가 데이터 등을 다룰 때 사용합니다.
- 함수는 `async def`로 정의해야 합니다.
- 응답은 `await update.message.reply_text(...)`처럼 보냅니다.

명령어 인자 받기 예시:

```python
from telegram import Update
from telegram.ext import ContextTypes


async def echo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: /echo 보낼말")
        return

    text = " ".join(context.args)
    await update.message.reply_text(text)
```

이 함수를 등록할 때는 `main.py`에서 아래처럼 추가합니다.

```python
app.add_handler(CommandHandler("echo", echo_command))
```

## 권장 파일 역할

- `main.py`: 봇 실행, 핸들러 등록
- `commands.py`: `/start`, `/help` 같은 명령어 함수 작성
- `TelegramBot.py`: 메시지 전송, 사진 전송, 파일 전송 같은 공통 Bot API 기능
- `config.py`: 텔레그램 토큰 등 설정값 관리

## 추천 개발 순서

1. `commands.py`에 `/start`, `/help` 함수 작성
2. `main.py`에서 `CommandHandler`로 등록
3. 필요하면 `TelegramBot` 클래스로 별도 알림 전송 기능 추가
4. 로컬에서 실행 후 텔레그램 채팅방에서 테스트
