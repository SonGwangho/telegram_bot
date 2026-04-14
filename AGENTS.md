# AGENTS.md

## 프로젝트 정보
- 프로젝트명: `telegram_bot`
- 프로젝트 버전: `0.1.1`
- 문서 버전: `1.1.0`
- 기준일: `2026-04-14`

## 프로젝트 목적
- `python-telegram-bot` 기반 텔레그램 챗봇 프로젝트
- 명령어 이벤트 함수는 `commands.py`에 작성
- 명령어 등록 및 봇 실행은 `main.py`에서 담당
- 공통 Bot API 기능은 `TelegramBot.py` 클래스에서 담당

## 현재 파일 구성
- `main.py`
  - 봇 애플리케이션 생성
  - `commands.py`의 명령어 함수 import
  - `CommandHandler` 등록
  - `run_polling()` 실행
- `commands.py`
  - `/start`, `/help` 같은 슬래시 명령어 이벤트 함수 작성
  - `Update`, `ContextTypes` 기반 비동기 핸들러 작성
- `TelegramBot.py`
  - 메시지 전송
  - 답장 전송
  - 이미지 전송
  - 문서 전송
  - 오디오 전송
  - 영상 전송
  - 미디어 그룹 전송
  - 메시지 수정 및 삭제
  - 파일 조회 및 다운로드
- `config.py`
  - `telegram_token` 관리
- `requirements.txt`
  - 프로젝트 의존성 관리
- `README.md`
  - 사용 방법 및 예제 문서

## 사용 버전
- Python: `3.10+` 권장
- 라이브러리: `python-telegram-bot==22.7`

## 설치 방법
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 실행 방법
기본 실행 파일은 `main.py`입니다.

```powershell
python main.py
```

## 현재 실행 구조
1. `main.py`에서 `Application` 생성
2. `commands.py`에서 명령어 함수 import
3. `CommandHandler("명령어", 함수)` 형태로 등록
4. `application.run_polling()`으로 봇 실행

예시 흐름:

```python
from telegram.ext import Application, CommandHandler

from commands import help_command, start_command
from config import telegram_token


def main() -> None:
    application = Application.builder().token(telegram_token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    application.run_polling()
```

## 명령어 작성 규칙
- 슬래시 명령어 함수는 `commands.py`에 작성
- 함수 형태는 `async def ... (update, context)` 사용
- 응답은 보통 `await update.message.reply_text(...)` 사용
- 새 명령어 추가 시 `main.py`에 반드시 핸들러 등록 필요

예시:

```python
async def hello_command(update, context):
    await update.message.reply_text("hello")
```

등록 예시:

```python
application.add_handler(CommandHandler("hello", hello_command))
```

## TelegramBot 클래스 사용 규칙
- `TelegramBot.py`는 핸들러 등록용 파일이 아니라 공통 전송 기능 모음 파일
- 토큰은 기본적으로 `config.py`의 `telegram_token` 사용
- 메서드는 `async` 기반이므로 `await` 필요
- 명령어 핸들러 내부 또는 별도 비동기 로직에서 호출 가능

주요 메서드:
- `send_message`
- `reply_message`
- `send_photo`
- `send_document`
- `send_audio`
- `send_video`
- `send_media_group`
- `send_chat_action`
- `edit_message_text`
- `delete_message`
- `download_file`

## 개발 원칙
- 명령어 로직과 봇 실행 로직을 분리
- 공통 API 호출은 `TelegramBot` 클래스에 모아 재사용
- 설정값은 `config.py`에서 관리
- 문서 예제와 실제 코드 구조를 최대한 일치시킬 것

## 다음 확장 후보
1. `commands.py`에 명령어 추가
2. 일반 메시지 처리용 `MessageHandler` 도입
3. 인라인 버튼 및 콜백 처리 추가
4. 토큰을 환경 변수 또는 `.env`로 분리
