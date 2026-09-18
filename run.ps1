# NebulaX PS1 backend - Windows launcher.
# Usage:  .\run.ps1            (port 8000)
#         .\run.ps1 -Port 8020
param([int]$Port = 8000)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

py -m pip install -r requirements.txt
py -m uvicorn app.main:app --host 0.0.0.0 --port $Port
