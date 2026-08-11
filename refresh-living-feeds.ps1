# Refresh Twin Lakes living feeds for The Ripple Effect StoryMap
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py = Join-Path (Split-Path -Parent $Root) ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = Join-Path $Root ".venv\Scripts\python.exe"
}
if (-not (Test-Path $Py)) {
    Write-Host "Python venv not found."
    exit 1
}
Set-Location $Root
& $Py src\08_refresh_living_feeds.py @args
