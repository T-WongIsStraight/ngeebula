import os
import uuid
import pandas as pd
from typing import List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, Response, HTTPException
from fastapi.responses import FileResponse
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

ALLOWED_FILENAMES = {
    "01_LINES.csv",
    "02_STATIONS.csv",
    "03_SECTORS.csv",
    "04_LOCATION_SUPPLY.csv",
    "05_BUFFER_LOCATION.csv",
    "06_PARAMETERS.csv",
    "07_PROJECT_DETAILS.csv",
    "08_ACTIVITY_DETAILS.csv",
}


class SolveRequest(BaseModel):
    scenario: str = "A"
    time_limit: float = 30.0
    workers: Optional[int] = 1


@app.get("/api/health")
def health_check():
    has_activities = os.path.exists(os.path.join(DATA_DIR, "08_ACTIVITY_DETAILS.csv"))
    return {"status": "ok", "service": "LTA Track Access Control API", "data_present": has_activities}


@app.get("/api/parameters")
def get_parameters():
    param_path = os.path.join(DATA_DIR, "06_PARAMETERS.csv")
    if not os.path.exists(param_path):
        raise HTTPException(
            status_code=400, detail="06_PARAMETERS.csv not found in data directory."
        )

    try:
        df_params = pd.read_csv(param_path)
        param_dict = dict(zip(df_params["key"], df_params["value"]))
        return {
            "start_date": str(param_dict["horizon_start"]),
            "horizon_weeks": int(param_dict["horizon_weeks"]),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to parse 06_PARAMETERS.csv: {exc}"
        )


@app.post("/api/upload-datasets")
async def upload_datasets(files: List[UploadFile] = File(...)):
    saved_files = []
    for file in files:
        # FIX B2: Sanitize filename to prevent path traversal
        clean_name = os.path.basename(file.filename)
        if clean_name not in ALLOWED_FILENAMES:
            raise HTTPException(
                status_code=400,
                detail=f"Rejected file '{clean_name}'. Must be one of: {sorted(ALLOWED_FILENAMES)}",
            )

        file_path = os.path.join(DATA_DIR, clean_name)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        saved_files.append(clean_name)

    return {"status": "success", "uploaded_files": saved_files}


@app.post("/api/solve")
def solve_scenario_endpoint(req: SolveRequest):
    # FIX B6: Endpoint uses POST to prevent side effects on GET
    scen_clean = req.scenario.upper()
    if scen_clean not in ["A", "B", "C"]:
        raise HTTPException(status_code=400, detail="Invalid scenario. Must be 'A', 'B', or 'C'.")

    try:
        instance_data = load_instance(DATA_DIR)
        result = solve_schedule(
            instance_data,
            scenario=scen_clean,
            time_limit_seconds=req.time_limit,
            num_workers=req.workers,
        )

        if result.get("status") != "success":
            return {
                "status": "infeasible",
                "solver_status": result.get("solver_status", "UNKNOWN"),
                "scenario": scen_clean,
                "message": result.get("message", "Solver failed to find a solution."),
            }

        # FIX B1 & B3: Unique job directory to prevent multi-user/multi-run file overwrites
        job_id = str(uuid.uuid4())[:8]
        job_output_dir = os.path.join(OUTPUT_DIR, "jobs", job_id)
        file_map = write_submission(result, job_output_dir)

        result["job_id"] = job_id
        result["download_urls"] = {
            name: f"/api/jobs/{job_id}/download/{name}" for name in file_map
        }
        return result

    except HTTPException:
        raise
    except Exception as exc:
        # FIX B5: Mask raw stack trace details in public error body
        raise HTTPException(status_code=500, detail=f"Solver error: {str(exc)}")


@app.get("/api/jobs/{job_id}/download/{filename}")
def download_job_file(job_id: str, filename: str):
    # FIX B8: Return proper FileResponse with attachment Disposition headers
    valid_files = ["SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv"]
    if filename not in valid_files:
        raise HTTPException(status_code=400, detail="Invalid submission filename requested.")

    file_path = os.path.join(OUTPUT_DIR, "jobs", job_id, filename)
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    raise HTTPException(status_code=404, detail=f"File {filename} for job {job_id} not found.")
