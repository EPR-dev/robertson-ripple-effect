# Launch the Robertson Rainforest community StoryMap (Streamlit)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Prefer project venv, then parent workstation venv
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = Join-Path (Split-Path -Parent $Root) ".venv\Scripts\python.exe"
}
if (-not (Test-Path $Py)) {
    Write-Host "Python venv not found."
    Write-Host "Create one with:  python -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -r requirements.txt"
    exit 1
}

$Gpkg = Join-Path $Root "outputs\geopackage\robertson_conservation.gpkg"
if (-not (Test-Path $Gpkg)) {
    Write-Host "Master GeoPackage missing:"
    Write-Host "  $Gpkg"
    Write-Host "If you cloned from GitHub, run:  git lfs pull"
    exit 1
}

Set-Location $Root
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"
Write-Host "Starting StoryMap with: $Py"
& $Py -m streamlit run dashboard\app.py --server.headless true --browser.gatherUsageStats false
