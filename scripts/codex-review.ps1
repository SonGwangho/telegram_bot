<#
.SYNOPSIS
  Codex 리뷰 래퍼 (Windows PowerShell)

.EXAMPLE
  .\scripts\codex-review.ps1                 # 커밋 안 된 변경분 리뷰
  .\scripts\codex-review.ps1 -Base main      # main 대비 브랜치 전체 리뷰
  .\scripts\codex-review.ps1 -Commit abc1234 # 특정 커밋 리뷰

  결과는 화면과 .codex-review.md 양쪽에 남습니다.
  .codex-review.md 는 .gitignore 에 추가하세요.

  실행 정책 때문에 막히면:
    powershell -ExecutionPolicy Bypass -File .\scripts\codex-review.ps1
#>

[CmdletBinding(DefaultParameterSetName = 'Uncommitted')]
param(
    [Parameter(ParameterSetName = 'Base')]
    [string]$Base,

    [Parameter(ParameterSetName = 'Commit')]
    [string]$Commit
)

$ErrorActionPreference = 'Stop'
$OutFile = '.codex-review.md'

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    Write-Error "codex 를 찾을 수 없습니다. 'npm i -g @openai/codex' 로 설치한 뒤 새 터미널을 여세요."
    exit 1
}

switch ($PSCmdlet.ParameterSetName) {
    'Base'   { $ReviewArgs = @('--base', $Base) }
    'Commit' { $ReviewArgs = @('--commit', $Commit) }
    default  { $ReviewArgs = @('--uncommitted') }
}

Write-Host "> codex --profile reviewer review $($ReviewArgs -join ' ')" -ForegroundColor Cyan

& codex --profile reviewer review @ReviewArgs | Tee-Object -FilePath $OutFile

Write-Host ""
Write-Host "> 결과 저장: $OutFile" -ForegroundColor Cyan
