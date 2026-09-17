from fastapi import FastAPI, HTTPException
import pandas as pd
from app.models import TaskUpdateSchema, TaskCreateSchema
from app.audit import record_audit, get_all_audit_logs
from app.solver import run_track_optimization

app = FastAPI(title="LTA Track Access Optimiser API")

# Load memory state
activities_df = pd.read_csv("08_ACTIVITY_DETAILS.csv")
projects_df = pd.read_csv("07_PROJECT_DETAILS.csv")
if "status" not in activities_df.columns:
    activities_df["status"] = "Not Started"

@app.get("/api/tasks")
def get_tasks():
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
        changes['status'] = {"old": activities_df.loc[row_idx, 'status'], "new": payload.status}
        activities_df.loc[row_idx, 'status'] = payload.status

    if payload.total_accesses is not None:
        changes['total_accesses'] = {"old": float(activities_df.loc[row_idx, 'total_accesses']), "new": payload.total_accesses}
        activities_df.loc[row_idx, 'total_accesses'] = payload.total_accesses

    log_id = record_audit(
        action_type="TASK_UPDATED",
        activity_id=payload.activity_id,
        author=payload.author,
        changes=changes,
        replan_triggered=True
    )
    return {"status": "success", "log_id": log_id}

@app.post("/api/tasks/create")
def create_task(payload: TaskCreateSchema):
    global activities_df
    new_task = payload.model_dump()
    new_task['status'] = "Not Started"
    author = new_task.pop('author')
    
    activities_df = pd.concat([activities_df, pd.DataFrame([new_task])], ignore_index=True)
    
    log_id = record_audit(
        action_type="TASK_CREATED",
        activity_id=payload.activity_id,
        author=author,
        changes={"created": new_task},
        replan_triggered=True
    )
    return {"status": "success", "log_id": log_id}

@app.get("/api/solve/{scenario}")
def solve_schedule(scenario: str):
    schedule = run_track_optimization(activities_df, projects_df, scenario=scenario)
    return schedule.to_dict(orient="records")

@app.get("/api/audit-log")
def fetch_audit_logs():
    return get_all_audit_logs()
