import os
import io
import pandas as pd
from typing import List, Dict, Any
from fastapi import FastAPI, UploadFile, File, Response, HTTPException
from app.solver import solve_schedule, load_instance, write_submission

app = FastAPI(title="LTA Track Access Optimiser API")

DATA_DIR = "data"
OUTPUT_DIR = "output"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_loaded_tables() -> Dict[str, Any]:
    """Helper to load all 8 required CSVs from the data folder."""
    try:
        return load_instance(DATA_DIR)
    except Exception as e:
        print(f"Warning: Could not load datasets from {DATA_DIR}: {e}")
        return {}


@app.get("/api/health")
def health_check():
    data = get_loaded_tables()
    has_data = bool(data and "activity_details" in data)
    return {
        "status": "ok",
        "loaded_activities": len(data.get("activity_details", [])) if has_data else 0
    }


@app.get("/api/parameters")
def get_parameters():
    data = get_loaded_tables()
    if data and "parameters" in data:
        params = {row.get("key"): row.get("value") for row in data["parameters"] if row.get("key")}
        return {
            "start_date": params.get("horizon_start", "2027-01-04"),
            "horizon_weeks": int(params.get("horizon_weeks", 30))
        }
    return {"start_date": "2027-01-04", "horizon_weeks": 30}


@app.post("/api/upload-datasets")
async def upload_datasets(files: List[UploadFile] = File(...)):
    saved_files = []
    for file in files:
        file_path = os.path.join(DATA_DIR, file.filename)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        saved_files.append(file.filename)

    return {"status": "success", "uploaded_files": saved_files}


@app.get("/api/solve/{scenario}")
def run_solver_endpoint(scenario: str, time_limit: float = 30.0):
    scenario_code = scenario.upper()
    if scenario_code not in {"A", "B", "C"}:
        raise HTTPException(status_code=400, detail="Scenario must be A, B, or C")

    data = get_loaded_tables()
    if not data or "activity_details" not in data:
        raise HTTPException(status_code=400, detail="Required CSV datasets (01-08) not uploaded yet.")

    # Execute your solver.py engine
    result = solve_schedule(
        data=data,
        scenario=scenario_code,
        time_limit_seconds=time_limit
    )

    if result.get("status") == "success":
        # Write the 3 official submission CSVs to output directory
        write_submission(result, OUTPUT_DIR)

    return result


@app.get("/api/download/{filename}")
def download_file(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content=content, media_type="text/csv")
    
    return Response(
        content="activity_id,access_seq,week,eclo,access_night\n", 
        media_type="text/csv"
    )
