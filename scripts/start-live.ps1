$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $projectRoot "src"

Set-Location $projectRoot
& (Join-Path $projectRoot ".venv\Scripts\python.exe") -m stock.web
