import os
import io
import pandas as pd
from typing import List
from fastapi import FastAPI, UploadFile, File, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.solver import load_instance, solve_schedule, write_submission

app = FastAPI(title="NebulaX PS1 Railway Track Access API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.getenv("DATA_DIR", "data")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "LTA Track Access Control API"}


@app.get("/api/parameters")
def get_parameters():
    param_path = os.path.join(DATA_DIR, "06_PARAMETERS.csv")
    if os.path.exists(param_path):
        try:
            df_params = pd.read_csv(param_path)
            if "key" in df_params.columns and "value" in df_params.columns:
                param_dict = dict(zip(df_params["key"], df_params["value"]))
                return {
                    "start_date": str(param_dict.get("horizon_start", "2027-01-04")),
                    "horizon_weeks": int(param_dict.get("horizon_weeks", 30))
                }
        except Exception as e:
            print(f"Error parsing parameters: {e}")
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
def solve_scenario_endpoint(
    scenario: str,
    time_limit: float = 30.0,
    workers: int = None
):
    scen_clean = scenario.upper()
    if scen_clean not in ["A", "B", "C"]:
        raise HTTPException(
            status_code=400, 
            detail="Invalid scenario. Must be 'A', 'B', or 'C'."
        )

    try:
        # Ingest datasets using solver's parser
        instance_data = load_instance(DATA_DIR)
        
        # Execute CP-SAT optimization model
        result = solve_schedule(
            instance_data,
            scenario=scen_clean,
            time_limit_seconds=time_limit,
            num_workers=workers
        )
        
        if result.get("status") != "success":
            raise HTTPException(
                status_code=500, 
                detail=result.get("message", "Solver failed to find a feasible solution.")
            )

        # Export official submission files
        write_submission(result, OUTPUT_DIR)
        
        return result

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/download/{filename}")
def download_submission_file(filename: str):
    valid_files = ["SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv"]
    if filename not in valid_files:
        raise HTTPException(status_code=400, detail="Invalid submission file request.")

    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content=content, media_type="text/csv")
    
    raise HTTPException(status_code=404, detail=f"File {filename} not generated yet.")
