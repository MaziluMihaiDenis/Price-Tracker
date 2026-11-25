# Restarts Price Tracker so it runs your latest code changes, then opens it in the browser.
#
#   powershell -ExecutionPolicy Bypass -File scripts\restart_app.ps1
#   (or double-click the "Restart Price Tracker" desktop icon: scripts\create_shortcut.ps1 makes it)
#
# What it does, in order:
#   1. Checks that the code loads (manage.py check). If not, it stops here and the running
#      app keeps working, so a typo never takes the app down for the family.
#   2. Stops Price Tracker's server (only its own pythonw.exe running scripts\serve.py).
#   3. Starts it again: through the "Price Tracker server" task if that's registered
#      (scripts\register_server.ps1), otherwise like the desktop icon.
#   4. Waits until it answers, opens the browser, and shows the last lines of logs\server.log.
#
# Options:  -NoBrowser   don't open the browser at the end
#           -Wait        keep the window open at the end (used by the desktop icon)

param([switch]$NoBrowser, [switch]$Wait)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$launcher = Join-Path $root 'scripts\open_app.pyw'
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$log = Join-Path $root 'logs\server.log'
$url = 'http://localhost:8000/'
$taskName = 'Price Tracker server'

function Finish([int]$code) {
    if ($Wait) { Read-Host 'Press Enter to close' | Out-Null }
    exit $code
}

function Get-ServerProcesses {
    # The project's pythonw.exe is a small starter that runs the real Python as its child;
    # both have "serve.py" on their command line, and both are stopped.
    @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
        Where-Object { $_.CommandLine -like '*scripts\serve.py*' })
}

function Test-PortListening {
    [bool](Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
}

function Test-Answering {
    try { Invoke-WebRequest -UseBasicParsing ($url + 'accounts/login/') -TimeoutSec 5 | Out-Null; $true }
    catch { $false }
}

try {
    if (-not (Test-Path $python)) { throw "Can't find $python. Create the virtual environment first (see README)." }

    # 1. Does the new code load? (Doesn't touch the database.)
    Write-Host 'Checking the code...'
    # 'Continue' here: in Windows PowerShell, error output from a program would otherwise
    # stop the script before it can show the error to you.
    $ErrorActionPreference = 'Continue'
    $check = & $python (Join-Path $root 'ui\manage.py') check 2>&1
    $checkFailed = $LASTEXITCODE -ne 0
    $ErrorActionPreference = 'Stop'
    if ($checkFailed) {
        Write-Host ''
        Write-Host ($check | Out-String)
        Write-Host 'The code has an error, so the app was NOT restarted (the running one keeps working).' -ForegroundColor Red
        Write-Host 'Fix the error above, then run this again.'
        Finish 1
    }

    # 2. Stop the running server.
    $old = Get-ServerProcesses
    if ($old.Count -gt 0) {
        Write-Host "Stopping Price Tracker (process $($old.ProcessId -join ', '))..."
        $old | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        for ($i = 0; $i -lt 20 -and (Test-PortListening); $i++) { Start-Sleep -Milliseconds 500 }
        if (Test-PortListening) {
            throw 'Port 8000 is still in use by another program (perhaps the development server). Stop it, then run this again.'
        }
    } elseif (Test-PortListening) {
        throw 'Port 8000 is used by another program (perhaps the development server: stop it with Ctrl+C), not by Price Tracker.'
    } else {
        Write-Host 'Price Tracker was not running.'
    }

    # 3. Start it again.
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    $startedByTask = $false
    if ($task) {
        try {
            Start-ScheduledTask -TaskName $taskName
            $startedByTask = $true
            Write-Host "Starting Price Tracker through the '$taskName' task..."
        } catch {
            Write-Host "Couldn't start the '$taskName' task ($($_.Exception.Message)); starting it directly instead."
        }
    }
    if (-not $startedByTask) {
        Write-Host 'Starting Price Tracker...'
        # open_app.pyw starts the server, waits for it and opens the browser (like the desktop icon)
        $env:BROWSER = $null
        if ($NoBrowser) { Start-Process -FilePath $pythonw -ArgumentList "`"$(Join-Path $root 'scripts\serve.py')`"" -WorkingDirectory $root }
        else { Start-Process -FilePath $pythonw -ArgumentList "`"$launcher`"" -WorkingDirectory $root }
    }

    # 4. Wait until it answers.
    $answering = $false
    for ($i = 0; $i -lt 60 -and -not $answering; $i++) { Start-Sleep -Milliseconds 500; $answering = Test-Answering }
    Write-Host ''
    if (Test-Path $log) { Get-Content $log -Tail 3 | ForEach-Object { Write-Host "  log: $_" } }
    if (-not $answering) {
        Write-Host "Price Tracker didn't answer within 30 seconds. Look at the end of $log for the reason." -ForegroundColor Red
        Finish 1
    }
    if ($startedByTask -and -not $NoBrowser) { Start-Process $url }
    Write-Host "Price Tracker restarted: $url (on the Wi-Fi: http://$($env:COMPUTERNAME):8000/)" -ForegroundColor Green
    Finish 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Finish 1
}
