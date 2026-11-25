# Puts a "Price Tracker" icon on your desktop (milestone 9). Clicking it opens the app in your
# browser, starting it first if it isn't running. Run once, from the project folder:
#
#   powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
#
# It points at "Price Tracker.exe" (with the app's green "P" icon) when that has been built
# (scripts\build_launcher.ps1); otherwise straight at Python. Running it again updates it.
# No administrator rights needed. To remove it, delete the icon from the desktop.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$script = Join-Path $root 'scripts\open_app.pyw'
$launcher = Join-Path $root 'Price Tracker.exe'
if (-not (Test-Path $pythonw)) { throw "Can't find $pythonw. Create the virtual environment first (see README)." }

$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Price Tracker.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
if (Test-Path $launcher) {
    $shortcut.TargetPath = $launcher
    $shortcut.Arguments = ''
    $shortcut.IconLocation = "$launcher,0"  # the green "P" built into the .exe
} else {
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = "`"$script`""
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,13"  # a globe-like Windows icon
    Write-Host 'Tip: build Price Tracker.exe first (scripts\build_launcher.ps1) for the app''s own icon.'
}
$shortcut.WorkingDirectory = $root
$shortcut.Description = 'Open Price Tracker'
$shortcut.Save()
Write-Host "Created $shortcutPath -> $($shortcut.TargetPath)"

# A second icon to restart the app after code changes (scripts\restart_app.ps1). A .ps1 file
# would open in Notepad when double-clicked, so the icon runs PowerShell with it instead.
$restartPath = Join-Path $desktop 'Restart Price Tracker.lnk'
$restart = $shell.CreateShortcut($restartPath)
$restart.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$restart.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $root 'scripts\restart_app.ps1')`" -Wait"
$restart.WorkingDirectory = $root
$restart.Description = 'Restart Price Tracker with the latest code'
$restart.IconLocation = "$env:SystemRoot\System32\shell32.dll,238"  # a circular "refresh" arrow
$restart.Save()
Write-Host "Created $restartPath"
