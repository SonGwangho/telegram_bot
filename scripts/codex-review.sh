#!/usr/bin/env bash
# 수동 리뷰 래퍼 (Git Bash 용). PowerShell 이면 codex-review.ps1 을 쓰세요.
#
#   ./scripts/codex-review.sh              # 커밋 안 된 변경분 리뷰
#   ./scripts/codex-review.sh main         # main 대비 브랜치 전체 리뷰
#   ./scripts/codex-review.sh --commit abc123
#
# 결과는 stdout 과 .codex-review.md 양쪽에 남는다.
# (.codex-review.md 는 .gitignore 에 추가하세요.)

set -euo pipefail

OUT=".codex-review.md"

if ! command -v codex >/dev/null 2>&1; then
  echo "codex 를 찾을 수 없습니다. 'npm i -g @openai/codex' 실행 후 새 터미널을 여세요." >&2
  exit 1
fi

case "${1:-}" in
  "")          ARGS=(--uncommitted) ;;
  --commit)    ARGS=(--commit "${2:?커밋 SHA 를 주세요}") ;;
  --*)         ARGS=("$@") ;;
  *)           ARGS=(--base "$1") ;;
esac

echo "▶ codex review ${ARGS[*]}" >&2
codex --profile reviewer review "${ARGS[@]}" | tee "$OUT"
echo "" >&2
echo "▶ 결과 저장: $OUT" >&2
