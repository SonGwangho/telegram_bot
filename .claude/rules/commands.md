---
paths:
  - "commands.py"
  - "main.py"
  - "hijack.py"
---

# 텔레그램 핸들러 작성 규칙

<!-- 이 규칙은 핸들러 관련 파일을 읽거나 쓸 때만 컨텍스트에 로드됩니다.
     AGENTS.md 를 비대하게 만들지 않으면서 세부 규칙을 유지하는 방법입니다. -->

- 슬래시 명령어 함수는 `commands.py` 에만 작성한다. 이름은 `<명령어>_command`.
- 시그니처는 `async def x_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None`.
- 새 명령어를 추가하면 `main.py` 에 `CommandHandler` 등록을 **반드시** 같이 넣는다.
  등록을 빠뜨린 명령어는 조용히 무반응이 되고 에러도 나지 않는다.
- `MessageHandler` 는 `group` 번호로 우선순위가 갈린다. 새로 추가할 때
  기존 그룹(`hijack_command`=2, `remember_message`=1)의 동작을 깨지 않는지 확인한다.
- 공통 전송 기능은 직접 `bot.send_*` 를 부르지 말고 `TelegramBot` 클래스를 쓴다.
- 사용자 입력은 그대로 출력하지 않는다. HTML 로 보낼 때는 `html.escape` 를 통과시킨다.
- 텔레그램 메시지는 4096자 제한이 있다. 길어질 수 있는 응답은 자르거나 나눈다.
- 블로킹 I/O(requests 등)는 핸들러에서 직접 호출하지 말고
  `asyncio.to_thread` 로 감싼다. 이벤트 루프를 막으면 봇 전체가 멈춘다.
- 외부 API 호출에는 타임아웃을 반드시 준다. 실패 시 사용자에게 보여줄 문구를 정한다.
- 예외를 조용히 삼키지 않는다. 사용자에게 알리거나 로깅 후 재발생시킨다.
