#!/usr/bin/env bash
# NebulaX PS1 backend - Linux/macOS launcher.  Usage: ./run.sh [port]
set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-${PORT:-8000}}"

python3 -m pip install -r requirements.txt
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
