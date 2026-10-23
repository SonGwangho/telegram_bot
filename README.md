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

## Windows 서비스 재시작 (`/restart`)

`/restart`는 `.env`의 `admin_user_id`에 지정된 사용자만 실행할 수 있습니다.
관리자 채팅방에 있다는 이유만으로 다른 사용자의 실행을 허용하지 않습니다.
봇은 먼저 요청 안내를 전송하고, Windows 작업 스케줄러의 `TelegramBot-Restart`
작업을 실행합니다. 이 작업은 봇과 독립적으로 서비스를 중지한 뒤 다시 시작합니다.
재기동 알림은 기존 `post_init`에서 `start_chat_id`로 전송합니다.

배포할 때와 봇이 시작할 때 작업을 자동 등록·갱신하므로 별도의 수동 설치는
필요하지 않습니다. `/restart`에서도 작업 설정을 확인한 후 실행합니다.
배포 계정에 관리자 권한이 있으면 배포 중에 등록하고, 그렇지 않으면 봇의
서비스 실행 계정으로 등록합니다. 최초 등록·갱신에는 둘 중 한 계정의 관리자
권한이 필요하며, 부족하면 자동 설정 실패를 로그에 남기고 일반 봇 기능은 계속 실행합니다.
기존 작업이 최신 상태이면 관리자 권한 없이 읽기·실행 권한만으로 사용합니다.

자동 등록 시 서비스 실행 계정을 찾아 작업 읽기·실행 권한을 부여합니다.
작업과 서비스 재시작 스크립트는 SYSTEM으로 실행되며, 스크립트는 관리자와
SYSTEM만 수정할 수 있는 `%ProgramFiles%\TelegramBot-Restart`에 복사됩니다.
서비스 실행 계정이나 재시작 스크립트가 바뀌면 다음 배포·기동 시 자동 갱신합니다.
봇 계정 자체가 관리자/SYSTEM이면 그 계정의 기존 권한은 그대로 적용됩니다.

배포된 봇에 `/restart`를 보내면 됩니다. 실행 중인 작업에 대한 추가
실행은 무시하고, 봇에서도 120초 동안 중복 요청을 막습니다. 봇 시작 전에 보낸
명령과 편집한 명령은 실행하지 않습니다. 작업 요청 실패는 채팅에 알리고,
실제 서비스 중지·시작 결과는 보호된 설치 폴더의 `restart.log`와 작업 스케줄러의
`LastTaskResult`에서 확인할 수 있습니다. 로그의 `running`은 Windows 서비스 상태이며
Telegram 연결 완료는 시작 알림으로 확인하세요.
Windows 서비스로 배포하지 않은 개발 환경에서는 이 기능을 사용하지 마세요.

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

## 리마인더 (`/r`)

`/r`만 보내면 입력 형식과 예시를 안내합니다.

```text
/r 30분 빨래 꺼내기
/r 2시간 약 먹기
/r 1시간 50분 노트북 챙기기
/r 2026-10-24 09:00 회의
/r 10-24 09:00 회의
/r 10월 24일 09:00 회의
/r 10월 24일 9시 30분 회의
```

- 상대 시간은 양의 정수 `분` 또는 `시간`으로 입력합니다.
  `1시간 50분`처럼 공백으로 구분해 함께 입력하면 모두 합산합니다.
- 날짜 지정은 `YYYY-MM-DD HH:MM`, `MM-DD HH:MM`, `MM월 DD일 HH:MM`
  형식을 지원하며 한국 시간(UTC+9) 기준입니다. `10월24일`처럼 붙여 써도 됩니다.
  날짜 뒤의 시각은 `9시 30분` 또는 `9시30분`처럼 입력해도 됩니다(24시간제).
  연도를 생략하면 올해로 해석하며, 이미 지난 날짜·시각은 등록하지 않습니다.
  날짜 없는 시각, 과거 시각, 존재하지 않는 날짜, 빈 내용은 받지 않습니다.
- 등록 후 실제 알림 예정 시각을 답장으로 안내하고, 시간이 되면 등록한 메시지에
  `⏰ 내용`을 답장합니다. 원래 메시지가 삭제됐다면 같은 채팅방에 전송합니다.
- 알림 시각·내용·채팅방·메시지·토픽·전송 결과를 `data/reminders.sqlite3`에 저장합니다.
  재기동 후 미전송 알림을 복구하며, 중지 중 시각이 지난 알림도 전송합니다.
  재기동이나 배포 시 이 DB를 보존해야 합니다.
- 전송 실패는 완료 처리하지 않고 재시도합니다. 전송 완료 기록이 있는 알림과
  같은 명령 메시지의 재전달은 중복 등록·전송하지 않습니다. 다만 Telegram 전송 성공과
  DB 완료 기록 사이에 프로세스가 강제 종료되면 재기동 후 중복 전송될 수 있습니다.
- 신규 패키지 없이 Python 표준 라이브러리 SQLite와 비동기 작업을 사용합니다.

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
  전체 길이는 실제 주제 수와 중요도에 맞추되, 각 주제는 결론과 핵심만 한 문장으로 압축합니다.
  꼭 필요한 결정이나 조건이 있을 때만 한 문장을 더 쓰고, 잡담·반복·발언 순서·세부 경위는 생략합니다.
  저장된 개수가 요청보다 적으면 실제 저장된 메시지만 사용합니다. 시작 안내 메시지 없이 요약 결과를 보냅니다.
  구간 요약은 동시에 최대 2개씩 요청합니다. 긴 기록은 API 호출과 비용이 늘어나며,
  전체 처리가 5분을 넘거나 구간 요약에 실패하면 부분 결과를 완성본으로 보내지 않고 실패를 알립니다.
- `/f [re] [질문]`: 비용과 응답 속도를 고려해 `gemini_model_lite`를 사용합니다.
  `/f re`는 오늘의 종합 운세를 캐시 없이 새로 생성합니다. `/f re 연애운`처럼 특정 질문도 재조회할 수 있습니다.
  재조회해도 같은 날짜·질문의 길흉 등급은 유지하며, 새로 생성한 결과를 저장해 이후 일반 `/f`에서 재사용합니다.
  생성이 실패하면 기존 캐시를 보존합니다.
  소재 100개·말투 14개에 상황 12개·전개 방식 8개·마무리 8개를 조합하며,
  사용자별 최근 3회에 쓴 소재와 표현 조합을 피합니다. 길흉 등급과 추첨 비율은 유지합니다.
  최근 운세 최대 14건과 본문 표현을 비교해 너무 비슷하면 한 번 더 생성하고,
  두 후보 중 최근 답변과 덜 비슷한 결과만 저장합니다. 재시도 중 API 오류가 나면 먼저 받은 정상 답변을 사용합니다.
  같은 사용자·한국 날짜·질문·등록 정보에는 저장된 답변을 재사용합니다.
  프롬프트 버전 변경 후에는 예전 답변을 새로 생성하고, 예전 기록은 반복 방지에만 참고합니다.
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
