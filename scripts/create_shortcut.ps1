# Puts a "Price Tracker" icon on your desktop (milestone 9). Clicking it opens the app in your
# browser, starting it first if it isn't running. Run once, from the project folder:
#
#   powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
#
# No administrator rights needed. To remove it, delete the icon from the desktop.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$script = Join-Path $root 'scripts\open_app.pyw'
if (-not (Test-Path $pythonw)) { throw "Can't find $pythonw. Create the virtual environment first (see README)." }

$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Price Tracker.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "`"$script`""
$shortcut.WorkingDirectory = $root
$shortcut.Description = 'Open Price Tracker'
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,13"  # a globe-like Windows icon
$shortcut.Save()
Write-Host "Created $shortcutPath"
