# Builds "Price Tracker.exe" in the project folder: a double-click launcher that starts the
# app if needed and opens it in the browser (see scripts\launcher\PriceTracker.cs).
#
# Uses the C# compiler that comes with Windows (.NET Framework 4), so nothing is installed.
# Run from the project folder (no administrator rights needed):
#
#   powershell -ExecutionPolicy Bypass -File scripts\build_launcher.ps1
#
# The .exe is a built file (git-ignored): rebuild it after changing PriceTracker.cs or the icon.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $compiler)) { $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe' }
if (-not (Test-Path $compiler)) { throw "Windows' C# compiler (.NET Framework 4) wasn't found: $compiler" }

$source = Join-Path $root 'scripts\launcher\PriceTracker.cs'
$icon = Join-Path $root 'scripts\launcher\price-tracker.ico'
$output = Join-Path $root 'Price Tracker.exe'

& $compiler /nologo /target:winexe /optimize+ /platform:anycpu `
    "/out:$output" "/win32icon:$icon" `
    /reference:System.Windows.Forms.dll `
    $source
if ($LASTEXITCODE -ne 0) { throw "The build failed (compiler exit code $LASTEXITCODE)." }

# Start-Process -Wait: PowerShell doesn't always wait for windowed programs like this one.
$check = Start-Process -FilePath $output -ArgumentList '--check' -Wait -PassThru
if ($check.ExitCode -ne 0) { throw "Built, but the launcher can't find .venv\Scripts\pythonw.exe or scripts\open_app.pyw." }
Write-Host "Built $output"
Write-Host 'Double-click it to open Price Tracker. For a desktop icon, run scripts\create_shortcut.ps1.'
