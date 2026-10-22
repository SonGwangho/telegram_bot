# Executed by the independent TelegramBot-Restart scheduled task as SYSTEM.
[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9_.-]+$')]
    [string]$BotServiceName = 'TelegramBot'
)

$ErrorActionPreference = 'Stop'
$logPath = Join-Path $PSScriptRoot 'restart.log'
$service = $null

function Write-RestartLog {
    param([string]$Message)
    Add-Content -LiteralPath $logPath -Value ("{0:o} {1}" -f (Get-Date), $Message) -Encoding UTF8
}

try {
    Write-RestartLog "Restart requested for $BotServiceName."
    # Give the command handler and polling acknowledgement time to finish.
    Start-Sleep -Seconds 3
    $service = Get-Service -Name $BotServiceName
    $timeout = [TimeSpan]::FromSeconds(45)
    if ($service.Status -eq 'StartPending') {
        $service.WaitForStatus('Running', $timeout)
    }
    if ($service.Status -ne 'Stopped') {
        if ($service.Status -ne 'StopPending') { $service.Stop() }
        $service.WaitForStatus('Stopped', $timeout)
    }
    $service.Start()
    $service.WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
    Write-RestartLog "$BotServiceName is running."
} catch {
    Write-RestartLog ("Restart failed: " + $_.Exception.Message)
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    if ($null -ne $service) { $service.Dispose() }
}
