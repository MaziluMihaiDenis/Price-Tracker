# Starts Price Tracker for the household whenever Windows starts, before anyone signs in
# (milestone 9). Run ONCE, as administrator, from the project folder:
#
#   1. Right-click Start > "Terminal (Admin)" or "Windows PowerShell (Admin)"
#   2. cd to this project folder
#   3. powershell -ExecutionPolicy Bypass -File scripts\register_server.ps1
#
# The task runs under your Windows account in "S4U" mode: it runs whether you're signed in
# or not, and Windows does NOT store your password. In this mode the task can only use this
# PC's own files and network (enough for the app, its database, backups in a local or
# OneDrive folder, and price checks over the internet).
#
# Remove it later with:
#   Unregister-ScheduledTask -TaskName 'Price Tracker server' -Confirm:$false

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal $identity).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw 'Please run this from an administrator terminal (see the top of this file).' }

$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$script = Join-Path $root 'scripts\serve.py'
if (-not (Test-Path $pythonw)) { throw "Can't find $pythonw. Create the virtual environment first (see README)." }

$taskName = 'Price Tracker server'
$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$script`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal `
    -Settings $settings -Description 'Runs Price Tracker for the household on port 8000 (scripts\serve.py).' -Force | Out-Null

Write-Host "Registered '$taskName' for $($identity.Name). It starts with Windows; starting it now..."
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 8
$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Host "State: $((Get-ScheduledTask -TaskName $taskName).State); last result: $($info.LastTaskResult) (0 or 267009 = running fine)"
Write-Host 'Open http://localhost:8000/ to check. The log is in logs\server.log.'
