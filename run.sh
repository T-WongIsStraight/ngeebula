#!/usr/bin/env bash

# Terminate background processes on script exit
trap "kill 0" EXIT

echo "=========================================================="
echo " 🚀 Launching LTA Track Access Control Center & Solver"
echo "=========================================================="

# Create necessary directories
mkdir -p database output

# Install Python dependencies if needed
if [ -f "requirements.txt" ]; then
    echo "📦 Checking and installing dependencies..."
    pip install -r requirements.txt --quiet
fi

# Initialize SQLite database
echo "🗄️ Initializing SQLite Audit Store..."
python3 -c "from app.audit import init_db; init_db()"

# Start FastAPI Backend Server
echo "⚡ Starting FastAPI Backend Server on port 8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &

# Wait for backend initialization
sleep 3

# Start Streamlit Frontend Dashboard
echo "🎨 Starting Streamlit Control Center Dashboard on port 8501..."
streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0

wait
