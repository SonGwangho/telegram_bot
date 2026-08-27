---
description: Codex 에게 현재 변경분 코드 리뷰를 요청하고 결과를 반영한다
argument-hint: "[base-branch | uncommitted]  (기본: uncommitted)"
allowed-tools: Bash(codex --profile reviewer:*), Bash(git status:*), Bash(git diff:*), Bash(python -m py_compile:*), PowerShell(codex --profile reviewer *), PowerShell(git status *), PowerShell(git diff *), Read, Edit, Write, Grep, Glob
---

## 리뷰 대상

인자: `$ARGUMENTS` (비어 있으면 `uncommitted`)

## 절차

1. `git status --short` 로 변경 범위를 먼저 확인한다.

2. Codex 리뷰를 실행한다. **셸 도구(Bash 또는 PowerShell)로 직접 실행**하고 완료까지
   기다린다. 리뷰는 수 분 걸릴 수 있다.

   - 인자가 비었거나 `uncommitted`:
     ```
     codex --profile reviewer review --uncommitted
     ```
   - 인자가 브랜치명:
     ```
     codex --profile reviewer review --base $ARGUMENTS
     ```

   `--profile reviewer` 를 절대 빠뜨리지 마라. 이 프로파일이 Codex 를 read-only 로
   묶어 두는 유일한 장치다. Codex 가 파일을 수정하려 하면 즉시 중단하고 보고한다.

3. 출력을 심각도별로 표로 정리한다: `등급 | 파일:라인 | 요약 | 내 판단`.

4. **BLOCKER / MAJOR** 를 수정한다. 수정 후 검증한다 (이 프로젝트는 테스트 스위트가
   없으므로 AGENTS.md 의 "검증" 절차를 따른다):

   ```
   python -m py_compile <수정한 파일들>
   ```

   핸들러 등록이나 import 를 건드렸다면 모듈 로딩까지 확인한다:

   ```
   python -c "import main"
   ```

   실제 봇 실행(`python main.py`)은 사용자 승인 없이 하지 않는다.

5. **동의하지 않는 지적**은 고치지 말고 표의 "내 판단" 칸에 반박 근거를 적는다.
   리뷰어는 전체 맥락 없이 판단하므로 오탐이 있을 수 있다.

6. 마지막에 다음 중 하나를 명확히 말한다:
   - `머지 가능` — BLOCKER/MAJOR 없음 또는 전부 해결됨
   - `재리뷰 필요` — 수정했으니 `/review` 를 한 번 더 돌려야 함
   - `사용자 판단 필요` — 오탐 여부나 설계 결정이 걸림

리뷰 결과를 근거로 코드를 고칠 때, 리뷰가 요청하지 않은 범위까지 손대지 않는다.
