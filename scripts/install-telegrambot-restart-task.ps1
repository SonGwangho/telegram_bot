# Called automatically by deployment and by the bot service.
# Registers the restart task without running it or restarting the bot.
[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9_.-]+$')]
    [string]$BotServiceName = 'TelegramBot',
    [switch]$IfNeeded
)

$ErrorActionPreference = 'Stop'
$service = Get-CimInstance Win32_Service -Filter "Name = '$BotServiceName'"
if ($null -eq $service) { throw "Service $BotServiceName was not found." }
$account = $service.StartName
switch -Regex ($account) {
    '^(LocalSystem|NT AUTHORITY\\SYSTEM)$' { $sid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18'); break }
    '^(NT AUTHORITY\\)?Network ?Service$' { $sid = [Security.Principal.SecurityIdentifier]::new('S-1-5-20'); break }
    '^(NT AUTHORITY\\)?Local ?Service$' { $sid = [Security.Principal.SecurityIdentifier]::new('S-1-5-19'); break }
    default {
        if ($account.StartsWith('.\')) { $account = $env:COMPUTERNAME + $account.Substring(1) }
        $sid = [Security.Principal.NTAccount]::new($account).Translate([Security.Principal.SecurityIdentifier])
    }
}

$taskName = 'TelegramBot-Restart'
$taskSource = 'telegram_bot /restart'
$sourcePath = Join-Path $PSScriptRoot 'restart-telegrambot.ps1'
$workerHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
$setupHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
$description = "Restart $BotServiceName; account=$($sid.Value); setup=$setupHash; worker=$workerHash"
$installDirectory = Join-Path $env:ProgramFiles 'TelegramBot-Restart'
$workerPath = Join-Path $installDirectory 'restart-telegrambot.ps1'
$powershellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$actionArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -BotServiceName "{1}"' -f $workerPath, $BotServiceName
$scheduler = New-Object -ComObject 'Schedule.Service'
$scheduler.Connect()
$root = $scheduler.GetFolder('\')
$existingTask = @($root.GetTasks(1) | Where-Object Name -eq $taskName)
if ($existingTask.Count -gt 0 -and $existingTask[0].Definition.RegistrationInfo.Source -ne $taskSource) {
    throw "An unrelated task named $taskName already exists. No changes were made."
}
if ($IfNeeded -and $existingTask.Count -gt 0) {
    $existingDefinition = $existingTask[0].Definition
    if ($existingTask[0].Enabled -and
        $existingDefinition.RegistrationInfo.Description -eq $description -and
        $existingDefinition.Principal.UserId -in @('SYSTEM', 'NT AUTHORITY\SYSTEM', 'S-1-5-18') -and
        $existingDefinition.Actions.Count -eq 1 -and
        $existingDefinition.Actions.Item(1).Path -eq $powershellPath -and
        $existingDefinition.Actions.Item(1).Arguments -eq $actionArguments) {
        Write-Host "$taskName is already configured."
        return
    }
}
if ($existingTask.Count -gt 0 -and $existingTask[0].State -eq 4) {
    throw 'The restart task is running. Wait for it to finish before installing again.'
}

$principal = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Automatic restart setup requires an elevated bot service or deployment account.'
}

# SYSTEM must not execute a script that the bot account can modify.
if ((Test-Path -LiteralPath $installDirectory) -and
    ((Get-Item -LiteralPath $installDirectory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'The installation directory must not be a reparse point.'
}
New-Item -ItemType Directory -Path $installDirectory -Force | Out-Null
$directoryAcl = [Security.AccessControl.DirectorySecurity]::new()
$directoryAcl.SetAccessRuleProtection($true, $false)
$directoryAcl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
foreach ($allowedSid in @('S-1-5-18', 'S-1-5-32-544')) {
    $rule = [Security.AccessControl.FileSystemAccessRule]::new(
        [Security.Principal.SecurityIdentifier]::new($allowedSid),
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit',
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow
    )
    $directoryAcl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $installDirectory -AclObject $directoryAcl
if ((Test-Path -LiteralPath $workerPath) -and
    ((Get-Item -LiteralPath $workerPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'The restart script must not be a reparse point.'
}
Copy-Item -LiteralPath $sourcePath -Destination $workerPath -Force
# Replace any explicit permissions left on a previous copy.
$fileAcl = [Security.AccessControl.FileSecurity]::new()
$fileAcl.SetAccessRuleProtection($true, $false)
$fileAcl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
foreach ($allowedSid in @('S-1-5-18', 'S-1-5-32-544')) {
    $fileAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        [Security.Principal.SecurityIdentifier]::new($allowedSid),
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow
    ))
}
Set-Acl -LiteralPath $workerPath -AclObject $fileAcl

$definition = $scheduler.NewTask(0)
$definition.RegistrationInfo.Source = $taskSource
$definition.RegistrationInfo.Description = $description
$definition.Principal.UserId = 'SYSTEM'
$definition.Principal.LogonType = 5 # TASK_LOGON_SERVICE_ACCOUNT
$definition.Principal.RunLevel = 1 # TASK_RUNLEVEL_HIGHEST
$definition.Settings.Enabled = $true
$definition.Settings.AllowDemandStart = $true
$definition.Settings.DisallowStartIfOnBatteries = $false
$definition.Settings.StopIfGoingOnBatteries = $false
$definition.Settings.MultipleInstances = 2 # TASK_INSTANCES_IGNORE_NEW
$definition.Settings.ExecutionTimeLimit = 'PT3M'
$action = $definition.Actions.Create(0) # TASK_ACTION_EXEC
$action.Path = $powershellPath
$action.Arguments = $actionArguments
$action.WorkingDirectory = $installDirectory

# The bot account may read/run this task, but cannot change its SYSTEM action.
$taskSddl = 'D:P(A;;GA;;;SY)(A;;GA;;;BA)'
if ($sid.Value -ne 'S-1-5-18') { $taskSddl += "(A;;GRGX;;;$($sid.Value))" }
$null = $root.RegisterTaskDefinition($taskName, $definition, 6, 'SYSTEM', $null, 5, $taskSddl)
Write-Host "Registered $taskName for service $BotServiceName."
Write-Host "Bot service account: $account; SID: $($sid.Value)"
Write-Host "Restart log: $(Join-Path $installDirectory 'restart.log')"
Write-Host 'The bot was not restarted. Send /restart as the configured admin to request a restart.'
