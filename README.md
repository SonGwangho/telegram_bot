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

## 모임 정산 기능

- `/adj 생성 모임명 인원수`: 현재 채팅방에 새 정산을 생성합니다.
- `/adj 모임명 이름 금액 [메모]`: 결제자, 결제 금액과 선택 메모를 등록합니다. 같은 이름을 여러 번 입력하면 금액은 누적되고 내역은 건별로 보존됩니다.
- `/adj 모임명`: 현재까지 등록된 건별 내역과 누적 총액을 조회합니다.
- `/adj 모임명 제거 숫자코드`: 내역 조회 시 표시된 4자리 코드의 결제 건을 삭제하고 누적 금액을 다시 계산합니다.
- `/adj 마감 모임명`: 각자의 부담액과 송금 경로를 안내한 뒤 해당 정산 데이터를 삭제합니다.
- 금액을 입력하지 않은 사람은 `미입력 인원`으로 자동 계산되며 송금 경로에서는 `인원 1`, `인원 2`처럼 표시됩니다.
- 1인 정산액과 최종 송금액은 100원 미만을 절사하며, 남은 우수리는 결제자가 부담합니다.
- 정산 모임은 텔레그램 채팅방별로 분리됩니다.
- 잔액이 남은 참여자가 12명 이하이면 최소 송금 횟수를 정확히 계산하고, 그보다 많으면 송금 횟수를 줄인 경로를 계산합니다.

예시:

```text
/adj 생성 여행 3
/adj 여행 철수 60000 숙소 결제
/adj 여행 영희 30000 장보기
/adj 마감 여행
```

## 주식 및 Gemini 기능

- `/stock`: 국내·해외 종목과 USD/KRW 환율을 동시에 조회합니다. 결과는 60초 동안 캐시하며, 일부 종목 조회가 실패해도 성공한 종목은 계속 표시합니다.
- `/chat 질문`: `gemini_model`을 우선 사용하고 실패하면 `gemini_model_lite`로 한 번 대체합니다.
- `/chat 초기화`: 현재 사용자와 현재 채팅방에 저장된 AI 대화 기록만 삭제합니다.
- `/sum 숫자`: 최근 지정한 개수의 메시지를 답장 맥락과 시간 흐름에 맞춰 `gemini_model_lite`로 요약합니다.
- `/f [질문]`: 비용과 응답 속도를 고려해 `gemini_model_lite`를 사용합니다.
- `/word`: `/reg`에 등록한 이름과 생년월일을 바탕으로 Gemini가 오늘의 맞춤 추천 문장과 관련 명언을 두 줄로 생성합니다. 같은 날짜와 사용자 정보에는 저장된 응답을 재사용합니다.

Gemini 대화 기록은 `gemini_data_file`에 저장되고 최대 2,000건을 유지합니다. Gemini API 호출이 모두 실패하면 기존 동작처럼 `제미나이 API 에러 - 원문` 형식으로 오류를 반환합니다.
