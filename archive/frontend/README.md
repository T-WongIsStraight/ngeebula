# Ngeebula frontend

Streamlit and Plotly dashboard for the rail-maintenance scheduler.

## Run locally

From this `frontend` folder:

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

The frontend looks for FastAPI at `http://127.0.0.1:8000` by default. Change the URL in the sidebar or set:

```powershell
$env:NGEEBULA_API_URL="http://127.0.0.1:8000"
```

If the backend is unavailable, the dashboard automatically uses `fakejason.json` so the prototype remains demonstrable.

## Backend endpoints used

- `GET /dashboard/gantt`
- `GET /alerts/`
- `GET /audit-logs/`
- `POST /schedule/propose`

The API client also includes helpers for the existing approval and checklist endpoints.
