#!/usr/bin/env bash

# Terminate background processes on exit
trap "kill 0" EXIT

echo "=========================================================="
echo " 🚀 Launching LTA Track Access Control Server"
echo "=========================================================="

# Enforce root module resolution for python imports
export PYTHONPATH=.

# Ensure required runtime directories exist
mkdir -p data output database

# Install python dependencies
if [ -f "requirements.txt" ]; then
    echo "📦 Checking and installing dependencies..."
    python3 -m pip install -r requirements.txt --quiet
fi

# Start FastAPI Backend Server
echo "⚡ Starting FastAPI Server on port 8000..."
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &

wait
