#!/usr/bin/env bash

# Terminate background processes on script exit
trap "kill 0" EXIT

echo "=========================================================="
echo " 🚀 Launching LTA Track Access Control Center & Solver"
echo "=========================================================="

# 1. Force Python to recognize current root directory for module imports
export PYTHONPATH=.

# 2. Ensure target runtime folders exist
mkdir -p database output app dashboard/components data

# 3. Mirror datasets to root directory if present in data/
if [ -d "data" ]; then
    cp data/*.csv . 2>/dev/null || true
fi

# 4. Check and install Python requirements
if [ -f "requirements.txt" ]; then
    echo "📦 Checking and installing dependencies..."
    python3 -m pip install -r requirements.txt --quiet
fi

# 5. Initialize SQLite Database Schema
echo "🗄️ Initializing SQLite Audit Store..."
python3 -c "from app.audit import init_db; init_db()"

# 6. Start FastAPI Backend Server
echo "⚡ Starting FastAPI Backend Server on port 8000..."
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &

# Allow FastAPI time to bind to port 8000
sleep 4

# 7. Start Streamlit Control Center Dashboard
echo "🎨 Starting Streamlit Control Center Dashboard on port 8501..."
python3 -m streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0

wait
