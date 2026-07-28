$ErrorActionPreference = "Stop"

py -3.13 -m pip install --user uv==0.11.33
py -3.13 -m uv sync --locked --extra dev
Write-Host "Environment ready. Run .\scripts\verify.ps1"
