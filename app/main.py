from fastapi import FastAPI, HTTPException, UploadFile, File, Response
import pandas as pd
import os
import io
from typing import List
from app.models import TaskUpdateSchema, TaskCreateSchema
from app.audit import record_audit, get_all_audit_logs
from app.solver import run_track_optimization
from app.data_loader import export_submission_files

app = FastAPI(title="LTA Track Access Optimiser API")

DATA_DIR = "data"
OUTPUT_DIR = "output"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Memory state dataframes
activities_df = pd.DataFrame()
projects_df = pd.DataFrame()

@app.post("/api/upload-datasets")
async def upload_datasets(files: List[UploadFile] = File(...)):
    global activities_df, projects_df
    saved_files = []
    
    for file in files:
        file_path = os.path.join(DATA_DIR, file.filename)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        saved_files.append(file.filename)
        
        # Auto-load into memory if activities or projects file uploaded
        if file.filename == "08_ACTIVITY_DETAILS.csv":
            activities_df = pd.read_csv(io.BytesIO(content))
            if "status" not in activities_df.columns:
                activities_df["status"] = "Not Started"
        elif file.filename == "07_PROJECT_DETAILS.csv":
            projects_df = pd.read_csv(io.BytesIO(content))

    record_audit(
        action_type="FILES_UPLOADED",
        activity_id="SYSTEM",
        author="Works_Controller_UI",
        changes={"uploaded_files": saved_files},
        replan_triggered=True
    )
    return {"status": "success", "uploaded_files": saved_files}

@app.get("/api/tasks")
def get_tasks():
    if activities_df.empty and os.path.exists(os.path.join(DATA_DIR, "08_ACTIVITY_DETAILS.csv")):
        global activities_df
        activities_df = pd.read_csv(os.path.join(DATA_DIR, "08_ACTIVITY_DETAILS.csv"))
        if "status" not in activities_df.columns:
            activities_df["status"] = "Not Started"
            
    return activities_df.to_dict(orient="records")

@app.post("/api/tasks/update")
def update_task(payload: TaskUpdateSchema):
    global activities_df
    idx = activities_df[activities_df['activity_id'] == payload.activity_id].index
    if idx.empty:
        raise HTTPException(status_code=404, detail="Task not found")
    
    changes = {}
    row_idx = idx[0]
    
    if payload.status and payload.status != activities_df.loc[row_idx, 'status']:
        changes['status'] = {"old": str(activities_df.loc[row_idx, 'status']), "new": payload.status}
        activities_df.loc[row_idx, 'status'] = payload.status

    log_id = record_audit(
        action_type="TASK_UPDATED",
        activity_id=payload.activity_id,
        author=payload.author,
        changes=changes,
        replan_triggered=True
    )
    return {"status": "success", "log_id": log_id}

@app.get("/api/solve/{scenario}")
def solve_schedule(scenario: str):
    global activities_df, projects_df
    
    if activities_df.empty and os.path.exists(os.path.join(DATA_DIR, "08_ACTIVITY_DETAILS.csv")):
        activities_df = pd.read_csv(os.path.join(DATA_DIR, "08_ACTIVITY_DETAILS.csv"))
    if projects_df.empty and os.path.exists(os.path.join(DATA_DIR, "07_PROJECT_DETAILS.csv")):
        projects_df = pd.read_csv(os.path.join(DATA_DIR, "07_PROJECT_DETAILS.csv"))
        
    access_df = run_track_optimization(activities_df, projects_df, scenario=scenario)
    
    # Generate dummy occupancy and results dfs matching schema
    occupancy_df = access_df[['activity_id', 'week']].copy() if not access_df.empty else pd.DataFrame(columns=['activity_id', 'week'])
    occupancy_df['location_id'] = "S01-ALP"
    occupancy_df['co_share_group'] = "GRP1"
    
    results_df = pd.DataFrame([{
        "scenario": scenario,
        "contract_number": "C101",
        "simulated_completion_date": "2026-12-31",
        "overrun_days": 0
    }])
    
    export_submission_files(access_df, occupancy_df, results_df, output_dir=OUTPUT_DIR)
    return access_df.to_dict(orient="records")

@app.get("/api/download/{filename}")
def download_file(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            content = f.read()
        return Response(content=content, media_type="text/csv")
    else:
        return Response(content="activity_id,access_seq,week,eclo,access_night\n", media_type="text/csv")

@app.get("/api/audit-log")
def fetch_audit_logs():
    return get_all_audit_logs()
