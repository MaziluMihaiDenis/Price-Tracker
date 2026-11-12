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
