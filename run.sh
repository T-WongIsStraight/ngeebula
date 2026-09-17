#!/usr/bin/env bash

# Terminate background processes on script exit
trap "kill 0" EXIT

echo "=========================================================="
echo " 🚀 Launching LTA Track Access Control Center & Solver"
echo "=========================================================="

# 1. Ensure Python module path includes current root directory
export PYTHONPATH=$(pwd)

# 2. Create required runtime directories
mkdir -p database output app dashboard/components

# 3. Check and install dependencies via python3 module
if [ -f "requirements.txt" ]; then
    echo "📦 Checking and installing dependencies..."
    python3 -m pip install -r requirements.txt --quiet
fi

# 4. Initialize SQLite Database
echo "🗄️ Initializing SQLite Audit Store..."
python3 -c "from app.audit import init_db; init_db()"

# 5. Start FastAPI Backend Server
echo "⚡ Starting FastAPI Backend Server on port 8000..."
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &

# Wait for backend initialization
sleep 3

# 6. Start Streamlit Frontend Dashboard
echo "🎨 Starting Streamlit Control Center Dashboard on port 8501..."
python3 -m streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0

wait
