# Registers the "Price Tracker daily check" task in Windows Task Scheduler.
#
# Run it once yourself, from an ADMINISTRATOR terminal in the project folder
# (right-click Start > "Terminal (Admin)"):
#     powershell -ExecutionPolicy Bypass -File scripts\register_daily_check.ps1
#
# The task runs every day at 17:00, and as soon as possible afterwards if the PC was off
# or asleep at 17:00. Like the household server, it runs whether anyone is signed in or not
# ("S4U": Windows does NOT store your password; the task can use this PC's own files and
# the internet, which is all the price check and the backup need).
# It starts Python directly (pythonw.exe: no console window), so it doesn't depend on
# PowerShell's script policy. Running this script again simply updates the task.

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal $identity).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw 'Please run this from an administrator terminal (see the top of this file).' }

$taskName = 'Price Tracker daily check'
$project = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $project '.venv\Scripts\pythonw.exe'
$uiFolder = Join-Path $project 'ui'
$logFile = Join-Path $project 'logs\daily_check.log'

if (-not (Test-Path $pythonw)) {
    throw "Python not found at $pythonw. Create the .venv first (see README.md)."
}
if (-not (Test-Path (Join-Path $uiFolder 'manage.py'))) {
    throw "manage.py not found in $uiFolder. Run this script from the project's scripts folder."
}

$action = New-ScheduledTaskAction -Execute $pythonw `
    -Argument "manage.py check_prices --log-file `"$logFile`"" `
    -WorkingDirectory $uiFolder
$trigger = New-ScheduledTaskTrigger -Daily -At '17:00'
# Store 17:00 as local time (no "Z"), so it stays 17:00 after summer/winter time changes.
$trigger.StartBoundary = (Get-Date -Hour 17 -Minute 0 -Second 0).ToString("yyyy-MM-dd'T'HH:mm:ss")
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
# S4U: runs even when nobody is signed in (e.g. the PC was switched on for the family's phones).
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType S4U -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force `
    -Description 'Checks the price of every automatically tracked item (Price Tracker).' | Out-Null

$task = Get-ScheduledTask -TaskName $taskName
Write-Host "Registered '$taskName'."
Write-Host ("  Runs daily at 17:00, catch-up after a missed start: " + $task.Settings.StartWhenAvailable)
Write-Host ("  Runs whether anyone is signed in or not, as " + $identity.Name + " (no password stored)")
Write-Host "  Program: $pythonw"
Write-Host "  Log file: $logFile"
Write-Host "To remove it later:  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
