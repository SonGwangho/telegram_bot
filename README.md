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

- `/ks`, `/us`: 국내·해외 종목을 각각 조회하며 USD/KRW 환율도 함께 조회합니다. 정상 결과는 60초 동안 캐시하며, 일부 종목 조회가 실패해도 성공한 종목은 계속 표시합니다.
- `/chat 질문`: `gemini_model`을 우선 사용하고 실패하면 `gemini_model_lite`로 한 번 대체합니다.
- `/chat 초기화`: 현재 사용자와 현재 채팅방에 저장된 AI 대화 기록만 삭제합니다.
- `/sum 숫자`: 최근 1~5,000개의 저장된 메시지를 답장 맥락과 시간 흐름에 맞춰 `gemini_model_lite`로 요약합니다. 예: `/sum 5000`.
  긴 기록은 최대 500개·약 48,000자 단위로 먼저 요약한 뒤 시간 순서대로 통합합니다.
  답변 길이는 실제 주제 수와 중요도에 맞추며, 긴 답변은 문단 경계를 우선해 여러 메시지로 나눠 보냅니다.
  요약 전용 지침을 사용하며 일반 AI 대화의 600자 제한은 적용하지 않습니다.
  저장된 개수가 요청보다 적으면 실제 저장된 메시지만 사용합니다. 시작 안내 메시지 없이 요약 결과를 보냅니다.
  구간 요약은 동시에 최대 2개씩 요청합니다. 긴 기록은 API 호출과 비용이 늘어나며,
  전체 처리가 5분을 넘거나 구간 요약에 실패하면 부분 결과를 완성본으로 보내지 않고 실패를 알립니다.
- `/f [질문]`: 비용과 응답 속도를 고려해 `gemini_model_lite`를 사용합니다.
- `/word`: `/reg`에 등록한 이름과 생년월일을 바탕으로 Gemini가 오늘의 맞춤 추천 문장과 관련 명언을 두 줄로 생성합니다. 같은 날짜와 사용자 정보에는 저장된 응답을 재사용합니다.

Gemini 대화 기록은 `gemini_data_file` 경로 뒤에 `.sqlite3`를 붙인 DB에 저장하고,
전체 최근 2,000건을 유지합니다. 예를 들어 `data/gemini_history.json` 설정은
`data/gemini_history.json.sqlite3`를 사용합니다. 사용자·채팅방별 최근 대화만 조회하며,
`/chat 초기화`는 해당 사용자·채팅방의 AI 대화만 삭제합니다.
기존 JSON은 최초 사용 시 한 번 이관하고 원본을 보존합니다. 손상된 JSON은 자동으로
빈 기록으로 대체하지 않습니다. 백업은 최신 DB 내용을 기존 JSON 배열 형식으로 내보내며,
기존 JSON 백업도 복원할 수 있습니다. `restore_data()`는 복원된 SQLite 경로를 반환합니다.
Gemini API 호출이 모두 실패하면 기존 동작처럼 `제미나이 API 에러 - 원문` 형식으로 오류를 반환합니다.

`/sum`용 채팅 기록은 `data/chat_room_history.sqlite3`에 방별 최근 5,000건을 저장합니다.
기존 2,000건 한도로 이미 삭제된 메시지는 복구되지 않으며, 새로 쌓이는 기록부터 확대된 한도를 적용합니다.
기존 `data/chat_room_history.json`이 있으면 최초 기록 저장·조회 시 한 번 이관하며,
원본 JSON은 수정하거나 삭제하지 않습니다. 이관 후 새 기록은 SQLite에만 저장됩니다.
메시지 수정은 기존 위치에 반영하고, 요약은 이전과 같이 오래된 메시지부터 순서대로 전달합니다.
SQLite는 Python 기본 모듈을 사용하므로 추가 패키지를 설치할 필요가 없습니다.

외부 조회는 `/bb` 60초, `/bbr`·`/uber` 30초, 주식·환율 60초 동안 메모리에 캐시합니다.
동일 조회가 동시에 들어오면 진행 중인 요청을 함께 기다립니다. 야구는 조회 날짜별,
주식은 시장·종목 목록별로 구분하며, 국내·해외 조회는 환율 결과를 공유합니다.
실패 응답은 저장하지 않고, 주식의 일부 종목이나 환율만 실패한 경우에도 다음 요청에서
다시 조회합니다. 캐시는 봇을 재시작하면 비워집니다.
