---
description: Codex 에게 QA(엣지케이스·실패 경로 점검)를 맡기고 결과를 반영한다
argument-hint: "<점검할 명령어/모듈>  (예: /adj, chat_history.py)"
allowed-tools: Bash(codex --profile reviewer:*), Bash(python -m py_compile:*), PowerShell(codex --profile reviewer *), Read, Edit, Write, Grep, Glob
---

## 대상

`$ARGUMENTS`

## 절차

1. 대상 코드를 먼저 읽는다. 명령어라면 `commands.py` 의 핸들러부터 시작해
   호출하는 모듈(`gemini.py`, `storage.py`, `myService.py`, `chat_history.py` 등)까지
   따라간다. 무엇을 점검해야 하는지 파악한 뒤 다음 단계로 간다.

2. QA 지시문을 프로젝트 루트의 `.codex-qa-prompt.txt` 에 쓴다.
   (셸 인용부호 문제를 피하려고 파일로 넘긴다. Windows PowerShell 에서 특히 중요하다.)

   내용 템플릿:

   ```
   QA 담당자로서 다음을 점검하라: <$ARGUMENTS 와 관련 파일 경로>

   이 프로젝트는 python-telegram-bot 기반 챗봇이고 자동화 테스트 스위트가 없다.
   따라서 "테스트를 짜라"가 아니라 "어떤 입력이 어떤 잘못된 결과를 내는지"를
   구체적으로 지목하라.

   1. 처리되지 않는 입력·상태를 나열하라
      (인자 없음/과다, 빈 문자열, 아주 긴 입력, 이모지·한글 인코딩,
       숫자 파싱 실패, 음수·0·상한 초과 금액, None 응답,
       Telegram 4096자 메시지 길이 제한, ParseMode 이스케이프 누락)
   2. 실패 경로를 점검하라
      (외부 API 타임아웃·비200 응답·스키마 변경, JSON 파일 손상,
       동시 호출 시 data/*.json 레이스, 예외를 조용히 삼키는 곳)
   3. 시간·환경 가정을 점검하라
      (Asia/Seoul 고정 가정, 자정 경계, 날짜 파싱, Windows 경로·CRLF)
   4. 각 항목마다 `파일:라인` 근거와 재현 입력을 써라
   5. 우선순위(HIGH/MED/LOW)를 매겨라
   6. 코드를 수정하지 말고 보고만 하라
   ```

3. 셸 도구로 실행하고 완료를 기다린다:

   ```
   codex --profile reviewer exec - < .codex-qa-prompt.txt
   ```

   PowerShell 에서 리다이렉션이 문제되면 다음을 쓴다:

   ```
   Get-Content .codex-qa-prompt.txt | codex --profile reviewer exec -
   ```

4. 끝나면 `.codex-qa-prompt.txt` 를 지운다.

5. 결과를 `우선순위 | 파일:라인 | 재현 입력 | 잘못된 결과 | 내 판단` 표로 정리한다.

6. **HIGH** 항목을 구현에서 고친다. 이 프로젝트는 **새 테스트 파일·디렉터리를 만들지 않는다**
   (AGENTS.md 개발 원칙). 검증은 다음으로 한다:

   ```
   python -m py_compile <수정한 파일들>
   python -c "import main"
   ```

   재현 입력을 실제로 태워 봐야 하는 항목은 사용자에게 수동 확인을 요청한다.

7. **의도된 동작이라 수정이 불필요한 항목**은 고치지 말고 표에 이유를 한 줄로 남긴다.
