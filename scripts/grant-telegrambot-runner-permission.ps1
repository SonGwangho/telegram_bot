# Run once in an administrator PowerShell on the deployment server.
[CmdletBinding()]
param(
    [string]$RunnerServiceName,
    [string]$BotServiceName = 'TelegramBot'
)

$ErrorActionPreference = 'Stop'

function Get-ServiceDaclWithRunnerAccess {
    param([string]$Sddl, [Security.Principal.SecurityIdentifier]$Sid)

    $descriptor = [Security.AccessControl.RawSecurityDescriptor]::new($Sddl)
    if ($null -eq $descriptor.DiscretionaryAcl) {
        throw 'The service has no DACL. Refusing to replace its security descriptor.'
    }

    # Query configuration/status, enumerate dependents, start and stop only.
    $requiredAccess = 0x003D
    $existingAccess = 0
    foreach ($ace in $descriptor.DiscretionaryAcl) {
        if ($ace -is [Security.AccessControl.CommonAce] -and $ace.SecurityIdentifier -eq $Sid) {
            if ($ace.AceQualifier -eq [Security.AccessControl.AceQualifier]::AccessDenied -and
                ($ace.AccessMask -band $requiredAccess) -ne 0) {
                throw 'An explicit deny blocks this account. Review the service DACL manually.'
            }
            if ($ace.AceQualifier -eq [Security.AccessControl.AceQualifier]::AccessAllowed) {
                $existingAccess = $existingAccess -bor $ace.AccessMask
            }
        }
    }

    $missingAccess = $requiredAccess -band (-bnot $existingAccess)
    if ($missingAccess -ne 0) {
        $newAce = [Security.AccessControl.CommonAce]::new(
            [Security.AccessControl.AceFlags]::None,
            [Security.AccessControl.AceQualifier]::AccessAllowed,
            $missingAccess, $Sid, $false, $null
        )
        $insertAt = $descriptor.DiscretionaryAcl.Count
        for ($index = 0; $index -lt $descriptor.DiscretionaryAcl.Count; $index++) {
            if ($descriptor.DiscretionaryAcl[$index].IsInherited) {
                $insertAt = $index
                break
            }
        }
        $descriptor.DiscretionaryAcl.InsertAce($insertAt, $newAce)
    }
    return $descriptor.GetSddlForm([Security.AccessControl.AccessControlSections]::Access)
}

function Get-RunningRunnerSid {
    $runnerProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'Runner.Listener.exe'")
    if ($runnerProcesses.Count -eq 0) {
        throw 'No running GitHub Actions runner was found. Keep the run.cmd window open and run this script again.'
    }
    $runnerSids = @($runnerProcesses | ForEach-Object {
        $owner = Invoke-CimMethod -InputObject $_ -MethodName GetOwnerSid
        if ($owner.ReturnValue -ne 0 -or [string]::IsNullOrWhiteSpace($owner.Sid)) {
            throw "Could not read the owner of runner process $($_.ProcessId). No permissions were changed."
        }
        $owner.Sid
    } | Sort-Object -Unique)
    if ($runnerSids.Count -ne 1) {
        throw 'Runners are running under different accounts. Supply -RunnerServiceName to select a specific runner service, or stop the other runners before trying again.'
    }
    return [Security.Principal.SecurityIdentifier]::new($runnerSids[0])
}

$principal = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Open PowerShell as Administrator on the deployment server, then run this script again.'
}

if ($RunnerServiceName) {
    $runnerServices = @(Get-CimInstance Win32_Service | Where-Object Name -eq $RunnerServiceName)
    if ($runnerServices.Count -ne 1) {
        throw 'The specified GitHub Actions runner service was not found. No permissions were changed.'
    }
    $account = $runnerServices[0].StartName
    switch -Regex ($account) {
        '^(LocalSystem|NT AUTHORITY\\SYSTEM)$' { $sid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18'); break }
        '^(NT AUTHORITY\\)?Network ?Service$' { $sid = [Security.Principal.SecurityIdentifier]::new('S-1-5-20'); break }
        '^(NT AUTHORITY\\)?Local ?Service$' { $sid = [Security.Principal.SecurityIdentifier]::new('S-1-5-19'); break }
        default {
            if ($account.StartsWith('.\')) { $account = $env:COMPUTERNAME + $account.Substring(1) }
            $sid = [Security.Principal.NTAccount]::new($account).Translate([Security.Principal.SecurityIdentifier])
        }
    }
} else {
    # Works for run.cmd in a terminal and for service-hosted runners.
    $sid = Get-RunningRunnerSid
    $account = $sid.Translate([Security.Principal.NTAccount]).Value
}

$botService = Get-Service -Name $BotServiceName
$scPath = Join-Path $env:SystemRoot 'System32\sc.exe'
$scOutput = & $scPath sdshow $BotServiceName
if ($LASTEXITCODE -ne 0) { throw 'sc.exe sdshow failed. No permissions were changed.' }
$sddlLines = @($scOutput | Where-Object { $_.Trim().StartsWith('D:') })
if ($sddlLines.Count -ne 1) { throw 'Could not read a unique service DACL. No permissions were changed.' }
$originalSddl = $sddlLines[0].Trim()
$updatedDacl = Get-ServiceDaclWithRunnerAccess -Sddl $originalSddl -Sid $sid
$originalDacl = [Security.AccessControl.RawSecurityDescriptor]::new($originalSddl).GetSddlForm(
    [Security.AccessControl.AccessControlSections]::Access
)

if ($updatedDacl -ne $originalDacl) {
    $backupDirectory = Join-Path $env:ProgramData 'TelegramBot\service-permissions'
    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
    $backupPath = Join-Path $backupDirectory (([guid]::NewGuid().ToString()) + '.sddl.txt')
    Set-Content -LiteralPath $backupPath -Value $originalSddl -Encoding ASCII
    & $scPath sdset $BotServiceName $updatedDacl
    if ($LASTEXITCODE -ne 0) { throw "sc.exe sdset failed. Original descriptor saved at $backupPath" }
    Write-Host "Original service permissions saved at: $backupPath"
}

Write-Host "Runner account: $account; SID: $($sid.Value)"
Write-Host "The runner now has query/start/stop access to $BotServiceName."
Restart-Service -Name $BotServiceName
$botService.WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
Write-Host "$BotServiceName is running. Retry the failed GitHub Actions deployment to verify runner access."
