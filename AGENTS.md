# AGENTS.md — 프로젝트 공용 규칙 (Single Source of Truth)

<!-- 이 파일이 두 도구의 공통 기준입니다.
     Codex 는 이 파일을 직접 읽고, Claude Code 는 CLAUDE.md 의 @AGENTS.md 임포트로 읽습니다.
     "이 프로젝트의 사실"만 적으세요. 도구별 행동 지침은 각자의 파일로 분리합니다. -->

## 프로젝트 정보
- 프로젝트명: `telegram_bot`
- 프로젝트 버전: `0.1.1`
- 문서 버전: `2.0.0`
- 기준일: `2026-08-27`

## 프로젝트 목적
- `python-telegram-bot` 기반 텔레그램 챗봇 프로젝트
- 명령어 이벤트 함수는 `commands.py`에 작성
- 명령어 등록 및 봇 실행은 `main.py`에서 담당
- 공통 Bot API 기능은 `TelegramBot.py` 클래스에서 담당
- AI 관련 기능은 `gemini.py` 클래스에서 담당

## 역할 분담 (AI 협업)
- **Claude Code = 구현.** 설계·구현·리팩터링·디버깅.
- **Codex = 리뷰 / QA.** `codex --profile reviewer review` 로 read-only 실행.
- 구현자가 자기 코드를 자기가 최종 승인하지 않는다. 아래 `Code Review Rules` 가 리뷰 기준이다.

## 현재 파일 구성

| 파일 | 역할 |
|------|------|
| `main.py` | `Application` 생성, 핸들러 등록, `run_polling()` 실행, 시작/종료 훅 |
| `commands.py` | 슬래시 명령어 이벤트 함수 (`/start`, `/help`, `/adj`, `/us` 등) |
| `TelegramBot.py` | 공통 Bot API 래퍼 클래스 (전송·수정·삭제·다운로드) |
| `gemini.py` | Gemini 연동 (대화, 요약, 추천 등 AI 기능) |
| `chat_history.py` | 채팅방 메시지 기록 캐시 및 요약용 포맷 |
| `hijack.py` | 일반 메시지 가로채기 (키워드 응답, URL 단축) |
| `adjustment.py` | 정산 기능 도메인 로직 |
| `appointment.py` | 외부 일정 API 조회 |
| `myService.py` | 주가·환율 등 외부 데이터 조회 |
| `word_recommendation.py` | 단어 추천 캐시·프롬프트 |
| `MyUtils.py` | 잡다한 유틸리티 |
| `storage.py` | `data/*.json` 읽기·쓰기 |
| `config.py` | `.env` 로부터 토큰·키·chat_id 로드 |
| `data/` | 런타임 JSON 데이터 (**커밋 금지, 읽지 말 것**) |
| `scripts/` | Codex 리뷰 래퍼 스크립트 |
| `requirements.txt` | 의존성 |
| `README.md` | 사용 방법 및 예제 문서 |

## 사용 버전
- Python: `3.10+` 권장 (현재 개발 환경 3.14)
- 주요 라이브러리: `python-telegram-bot==22.7`, `python-dotenv`, `requests`, `bs4`, `google-genai`

## 명령어

셸은 Windows 다. Git Bash 가 설치돼 있으면 Bash 를 쓰고, PowerShell 을 쓸 때는
`&&` 대신 `;` 를 쓰거나 명령을 나눠서 실행한다. 경로를 코드에 하드코딩할 때는
`pathlib.Path` 같은 플랫폼 중립 API 를 쓴다.

```powershell
python -m venv .venv                 # 최초 1회
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m py_compile commands.py     # 문법 검사 (변경한 파일)
python -c "import main"              # 모듈 로딩 확인
python main.py                       # 봇 실행 — 실제 텔레그램에 붙는다. 함부로 돌리지 말 것
```

**이 프로젝트에는 자동화 테스트 스위트가 없다.** 검증은 위의 문법 검사와
모듈 로딩 확인으로 한다.

## 현재 실행 구조
1. `main.py`에서 `Application` 생성 (`post_init` / `post_stop` / `post_shutdown` 훅 포함)
2. `commands.py`에서 명령어 함수 import
3. `CommandHandler("명령어", 함수)` 로 등록, 일반 메시지는 `MessageHandler` + `group` 으로 등록
4. `application.run_polling()`으로 봇 실행

## 명령어 작성 규칙
- 슬래시 명령어 함수는 `commands.py`에 작성하고 이름은 `<명령어>_command`
- 함수 형태는 `async def ...(update, context)` 사용
- 응답은 보통 `await update.message.reply_text(...)` 사용
- 새 명령어 추가 시 `main.py`에 반드시 핸들러 등록 필요

```python
# commands.py
async def hello_command(update, context):
    await update.message.reply_text("hello")

# main.py
application.add_handler(CommandHandler("hello", hello_command))
```

## TelegramBot 클래스 사용 규칙
- `TelegramBot.py`는 핸들러 등록용 파일이 아니라 공통 전송 기능 모음 파일
- 토큰은 기본적으로 `config.py`의 `telegram_token` 사용
- 메서드는 `async` 기반이므로 `await` 필요
- 주요 메서드: `send_message`, `reply_message`, `send_photo`, `send_document`,
  `send_audio`, `send_video`, `send_media_group`, `send_chat_action`,
  `edit_message_text`, `delete_message`, `download_file`

## 개발 원칙
- 명령어 로직과 봇 실행 로직을 분리
- 공통 API 호출은 `TelegramBot` 클래스에 모아 재사용
- 설정값은 `config.py`에서 관리하고, 값 자체는 `.env` 에 둔다
- 문서 예제와 실제 코드 구조를 최대한 일치시킬 것
- **별도의 테스트 파일이나 테스트 디렉터리를 새로 만들지 말 것**
- 변경 사항은 문법 검사와 모듈 로딩 확인으로 검증할 것
- 예외는 삼키지 않는다. 사용자에게 알리거나 로깅 후 재발생시킨다
- 블로킹 I/O 는 `asyncio.to_thread` 로 감싼다. 이벤트 루프를 막으면 봇 전체가 멈춘다
- 외부 API 호출에는 타임아웃을 반드시 준다
- 신규 의존성 추가 전에 사람에게 먼저 확인한다
- 시크릿·토큰·chat_id 를 코드나 로그에 하드코딩하지 않는다

## 커밋
- 커밋 전 문법 검사·모듈 로딩 확인 통과 필수
- `.env`, `data/`, `__pycache__/` 는 커밋하지 않는다
- `git push --force` 금지

---

## Code Review Rules

<!-- Codex 전용 섹션. Codex 의 코드 리뷰가 이 규칙을 기준으로 동작합니다.
     Claude 도 CLAUDE.md 임포트를 통해 이 내용을 보므로,
     "리뷰에서 뭘 볼지"를 미리 알고 코드를 쓰게 되는 효과가 있습니다. -->

리뷰어는 **코드를 수정하지 않는다.** 문제를 찾아 보고만 한다.

### 심각도 기준

| 등급 | 정의 | 조치 |
|------|------|------|
| **BLOCKER** | 데이터 손실, 시크릿 노출, 봇 크래시·행 유발 | 머지 불가 |
| **MAJOR** | 명백한 로직 오류, 처리되지 않은 에러 경로, 계약 위반 | 머지 전 수정 |
| **MINOR** | 가독성, 네이밍, 중복 | 선택 수정 |
| **NIT** | 취향 문제 | 언급만 |

### 반드시 확인할 것

1. **정확성** — 경계값, off-by-one, `None`, 빈 컬렉션, 금액/수량 파싱, 타임존(Asia/Seoul)
2. **에러 처리** — 실패 경로가 있는가. 예외를 조용히 삼키는 곳은 없는가
3. **텔레그램 계약** — 핸들러 등록 누락, 4096자 메시지 길이 제한,
   `ParseMode` 사용 시 사용자 입력 이스케이프(`html.escape`) 누락,
   `update.message` 가 `None` 일 수 있는 경로
4. **비동기/자원** — 이벤트 루프를 막는 블로킹 호출, 타임아웃 없는 외부 요청,
   닫히지 않는 세션·파일 핸들
5. **데이터 정합성** — `data/*.json` 동시 쓰기 레이스, 부분 쓰기로 인한 손상,
   스키마 변경 시 기존 파일 하위 호환
6. **보안** — 시크릿·토큰·chat_id 노출, 미검증 사용자 입력, 권한(관리자) 체크 누락
7. **회귀** — 기존 호출부의 시그니처·동작이 깨지지 않는가
8. **Windows 이식성** — 하드코딩된 경로 구분자, 인코딩 미지정 파일 I/O,
   CRLF/LF 가정, 파일 잠금

### 하지 말 것

- 스타일만 지적하고 끝내지 말 것 (린터가 할 일이다)
- 요청 범위 밖의 리팩터링 제안 금지
- 테스트 파일 신설 요구 금지 (이 프로젝트는 테스트 스위트를 두지 않는다).
  대신 "어떤 입력이 어떤 잘못된 결과를 내는지"를 구체적으로 지목할 것
- 추측성 지적 금지. 근거가 되는 `파일:라인` 을 반드시 제시할 것

### 출력 형식

발견 항목마다:

```
[BLOCKER] commands.py:142
문제: 사용자 입력이 이스케이프 없이 HTML ParseMode 로 전송됨
영향: 특정 입력에서 메시지 전송이 실패하거나 마크업이 깨짐
근거: `reply_text(f"<b>{text}</b>", parse_mode="HTML")`
제안: `html.escape(text)` 를 통과시킬 것
```

마지막에 한 줄 판정: `APPROVE` / `REQUEST_CHANGES` / `BLOCK`
