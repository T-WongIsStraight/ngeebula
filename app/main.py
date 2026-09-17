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

# Global in-memory dataframes
activities_df = pd.DataFrame()
projects_df = pd.DataFrame()

@app.get("/api/health")
def health_check():
    return {"status": "ok", "loaded_tasks": len(activities_df)}

@app.get("/api/parameters")
def get_parameters():
    param_path = os.path.join(DATA_DIR, "06_PARAMETERS.csv")
    if os.path.exists(param_path):
        try:
            df_params = pd.read_csv(param_path)
            # Schema mapping: key, value
            if "key" in df_params.columns and "value" in df_params.columns:
                param_dict = dict(zip(df_params['key'], df_params['value']))
                start_date = str(param_dict.get("horizon_start", "2027-01-04"))
                horizon_weeks = int(param_dict.get("horizon_weeks", 30))
                return {"start_date": start_date, "horizon_weeks": horizon_weeks}
        except Exception as e:
            print(f"Error reading 06_PARAMETERS.csv: {e}")
    return {"start_date": "2027-01-04", "horizon_weeks": 30}

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
    global activities_df
    if activities_df.empty and os.path.exists(os.path.join(DATA_DIR, "08_ACTIVITY_DETAILS.csv")):
        activities_df = pd.read_csv(os.path.join(DATA_DIR, "08_ACTIVITY_DETAILS.csv"))
        if "status" not in activities_df.columns:
            activities_df["status"] = "Not Started"
            
    return activities_df.to_dict(orient="records")

@app.post("/api/tasks/update")
def update_task(payload: TaskUpdateSchema):
    global activities_df
    if activities_df.empty:
        raise HTTPException(status_code=400, detail="No activity data loaded.")
        
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
        
    # 1. Run CP-SAT optimization solver
    access_df = run_track_optimization(activities_df, projects_df, scenario=scenario)
    
    # 2. Build SCHEDULE_OCCUPANCY dynamically
    if not access_df.empty and not activities_df.empty:
        merged_occ = access_df.merge(activities_df, on="activity_id", how="left")
        occupancy_cols = ['activity_id', 'week', 'location_id', 'co_share_group']
        for col in occupancy_cols:
            if col not in merged_occ.columns:
                merged_occ[col] = "GRP1" if col == "co_share_group" else "LOC_DEFAULT"
        occupancy_df = merged_occ[occupancy_cols].copy()
    else:
        occupancy_df = pd.DataFrame(columns=['activity_id', 'week', 'location_id', 'co_share_group'])
    
    # 3. Build RESULTS dynamically per contract with type-safe matching
    results_records = []
    if not access_df.empty and not projects_df.empty:
        # Cast key columns to string to guarantee merge matching
        activities_df['activity_id'] = activities_df['activity_id'].astype(str)
        access_df['activity_id'] = access_df['activity_id'].astype(str)
        
        merged = access_df.merge(
            activities_df[['activity_id', 'contract_number']], 
            on="activity_id", 
            how="inner"
        )
        
        merged['contract_number'] = merged['contract_number'].astype(str).str.strip()
        contract_max_week = merged.groupby('contract_number')['week'].max().to_dict()
        
        # Read horizon_start base date from 06_PARAMETERS.csv
        base_date = pd.to_datetime("2027-01-04")
        param_path = os.path.join(DATA_DIR, "06_PARAMETERS.csv")
        if os.path.exists(param_path):
            try:
                dp = pd.read_csv(param_path)
                if "key" in dp.columns and "value" in dp.columns:
                    pdict = dict(zip(dp['key'], dp['value']))
                    base_date = pd.to_datetime(pdict.get("horizon_start", "2027-01-04"))
            except Exception:
                pass

        for _, proj in projects_df.iterrows():
            c_num = str(proj.get('contract_number', '')).strip()
            
            # Look up max scheduled week for this contract
            max_w = contract_max_week.get(c_num)
            
            if max_w is not None:
                comp_date = base_date + pd.Timedelta(weeks=int(max_w))
                comp_date_str = comp_date.strftime("%Y-%m-%d")
            else:
                comp_date = base_date
                comp_date_str = base_date.strftime("%Y-%m-%d")
            
            target_date_str = str(proj.get('target_completion_date', '2027-12-31'))
            try:
                target_date = pd.to_datetime(target_date_str)
                overrun = max(0, (comp_date - target_date).days) if max_w else 0
            except Exception:
                overrun = 0
            
            results_records.append({
                "scenario": scenario,
                "contract_number": c_num,
                "simulated_completion_date": comp_date_str,
                "overrun_days": overrun
            })
            
        results_df = pd.DataFrame(results_records)
    else:
        results_df = pd.DataFrame(columns=["scenario", "contract_number", "simulated_completion_date", "overrun_days"])
    
    # 4. Export submission files
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
