# main.py
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import datetime
import json
from typing import List, Optional, Dict, Any
from google import genai

import database
import solver  # Solver teammate logic imported cleanly here

database.init_db()

app = FastAPI(title="SMRT Railway Maintenance System Backend", version="3.0")
client = genai.Client()

STATUS_COLORS = {
    "Done": "Green",
    "Error": "Red",
    "Delay": "Orange",
    "In progress": "Blue",
    "Not started": "Black"
}

# --- Pydantic Schemas ---
class JobInput(BaseModel):
    name: str
    description: str
    line: str
    track: str
    deadline: datetime.datetime

class ApprovalPayload(BaseModel):
    approved: bool
    approved_by: str
    override_start_min: Optional[int] = None
    override_priority: Optional[str] = None
    override_engineers: Optional[List[int]] = None

class ChecklistUpdate(BaseModel):
    status: str
    updated_by: str
    reason: Optional[str] = None
    updated_repair_time_mins: Optional[int] = None

# --- Dependency ---
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Helper Functions ---
def get_color(status: str) -> str:
    return STATUS_COLORS.get(status, "Black")

def minutes_to_datetime(min_offset: int) -> datetime.datetime:
    now = datetime.datetime.now(datetime.timezone.utc)
    base_window_start = now.replace(hour=0, minute=30, second=0, microsecond=0)
    if now.hour >= 5:
        base_window_start += datetime.timedelta(days=1)
    return base_window_start + datetime.timedelta(minutes=min_offset)

# --- Routes ---

@app.post("/jobs/parse-and-create", response_model=Dict[str, Any])
def parse_job_and_create(job_in: JobInput, db: Session = Depends(get_db)):
    """AI parses raw user input, infers metadata, and saves to database."""
    prompt = f"""
    Analyze this SMRT maintenance task:
    Title: {job_in.name}
    Description: {job_in.description}
    Deadline: {job_in.deadline.isoformat()}
    
    Infer the following fields in strict JSON format:
    - "priority": one of ["Urgent", "High", "Medium", "Low"]
    - "effort_level": integer 1 to 5
    - "duration_mins": estimated repair duration in minutes (e.g. 30, 45, 60, 90)
    - "required_skill": specific skill needed
    - "engineers_needed": integer (2 to 5)
    """
    
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        cleaned = response.text.strip().lstrip("```json").rstrip("```").strip()
        ai_data = json.loads(cleaned)
    except Exception:
        ai_data = {"priority": "Medium", "effort_level": 3, "duration_mins": 60, "required_skill": "General maintenance", "engineers_needed": 2}

    db_job = database.RepairJob(
        name=job_in.name,
        description=job_in.description,
        line=job_in.line,
        track=job_in.track,
        deadline=job_in.deadline,
        priority=ai_data.get("priority", "Medium"),
        effort_level=ai_data.get("effort_level", 3),
        duration_mins=ai_data.get("duration_mins", 60),
        required_skill=ai_data.get("required_skill", "General maintenance"),
        engineers_needed=ai_data.get("engineers_needed", 2),
        status="Not started",
        status_color=get_color("Not started"),
        is_approved=False
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)

    return {"status": "success", "job_id": db_job.id, "parsed_data": ai_data}

@app.post("/schedule/propose", response_model=Dict[str, Any])
def propose_schedule_options(db: Session = Depends(get_db)):
    """Fetches DB data, calls solver module, returns 3 AI-suggested options."""
    jobs_db = db.query(database.RepairJob).filter(database.RepairJob.status != "Done").all()
    engineers_db = db.query(database.Engineer).all()

    jobs_data = [{
        "id": j.id,
        "line": j.line,
        "track": j.track,
        "duration_mins": j.duration_mins,
        "priority": j.priority,
        "required_skill": j.required_skill,
        "engineers_needed": j.engineers_needed
    } for j in jobs_db]

    engineers_data = [{
        "id": e.id,
        "name": e.name,
        "years_of_experience": e.years_of_experience,
        "job_role": e.job_role,
        "specialized_line": e.specialized_line,
        "is_available": e.is_available,
        "skills": [s.skill_name for s in e.skills]
    } for e in engineers_db]

    schedule_results = solver.solve_mrt_schedule(jobs_data, engineers_data)

    if not schedule_results:
        raise HTTPException(status_code=400, detail="Solver could not generate a feasible schedule.")

    base_schedule = []
    for res in schedule_results:
        job = db.query(database.RepairJob).filter(database.RepairJob.id == res["id"]).first()
        if job:
            start_dt = minutes_to_datetime(res["scheduled_start_min"])
            end_dt = minutes_to_datetime(res["scheduled_end_min"])
            base_schedule.append({
                "job_id": job.id,
                "name": job.name,
                "line": job.line,
                "track": job.track,
                "priority": job.priority,
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
                "assigned_engineer_ids": res["assigned_engineer_ids"]
            })

    prompt = f"Given this baseline schedule: {json.dumps(base_schedule)}. Output 3 JSON options: Option 1: Optimal, Option 2: Priority-Focused, Option 3: Balanced Workload."
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        cleaned = response.text.strip().lstrip("```json").rstrip("```").strip()
        options = json.loads(cleaned)
    except Exception:
        options = [{"option_name": "Option 1: Recommended", "schedule": base_schedule}]

    return {"status": "success", "options": options, "base_schedule": base_schedule}

@app.post("/approval/{job_id}", response_model=Dict[str, Any])
def approve_or_override_job(job_id: int, payload: ApprovalPayload, db: Session = Depends(get_db)):
    """Handles higher-up approval and manual overrides."""
    job = db.query(database.RepairJob).filter(database.RepairJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    action_text = "Approved" if payload.approved else "Rejected/Overridden"
    if payload.approved:
        job.is_approved = True
        if payload.override_start_min is not None:
            job.scheduled_start_min = payload.override_start_min
            job.scheduled_end_min = payload.override_start_min + job.duration_mins
            job.scheduled_start = minutes_to_datetime(job.scheduled_start_min)
            job.scheduled_end = minutes_to_datetime(job.scheduled_end_min)
        if payload.override_priority:
            job.priority = payload.override_priority
        if payload.override_engineers:
            engineers = db.query(database.Engineer).filter(database.Engineer.id.in_(payload.override_engineers)).all()
            job.assigned_engineers = engineers
    else:
        job.is_approved = False

    audit = database.AuditLog(
        action=action_text,
        details=f"Job {job_id} ({job.name}) {action_text.lower()} by {payload.approved_by}.",
        approved_by=payload.approved_by
    )
    db.add(audit)
    db.commit()

    return {"status": "success", "action": action_text}

@app.patch("/checklist/{job_id}", response_model=Dict[str, Any])
def update_checklist_status(job_id: int, payload: ChecklistUpdate, db: Session = Depends(get_db)):
    """Updates status, color codes, handles engineer availability, and triggers AI for delays/errors."""
    job = db.query(database.RepairJob).filter(database.RepairJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    new_status = payload.status
    job.status = new_status
    job.status_color = get_color(new_status)
    ai_action_summary = None

    if new_status == "Done":
        for eng in job.assigned_engineers:
            eng.is_available = True
        job.assigned_engineers = []
    elif new_status in ("Delay", "Error"):
        if new_status == "Delay":
            job.delay_reason = payload.reason
            if payload.updated_repair_time_mins:
                job.duration_mins = payload.updated_repair_time_mins
        else:
            job.error_reason = payload.reason
            
        prompt = f"Repair Job '{job.name}' status changed to {new_status}. Reason: '{payload.reason}'. Suggest revised schedule and next action."
        res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        ai_action_summary = res.text if res else "AI recommends shifting to next available window."
        job.ai_suggested_action = ai_action_summary
        job.is_approved = False

    audit = database.AuditLog(
        action=f"Status -> {new_status}",
        details=f"Job {job_id} updated to {new_status} by {payload.updated_by}. Reason: {payload.reason or 'N/A'}",
        approved_by=payload.updated_by
    )
    db.add(audit)
    db.commit()

    return {"status": "success", "job_id": job_id, "new_status": new_status, "status_color": job.status_color, "ai_suggested_action": ai_action_summary}

@app.get("/dashboard/gantt", response_model=List[Dict[str, Any]])
def get_gantt_chart_data(db: Session = Depends(get_db)):
    """Serves Gantt chart data with color coding."""
    jobs = db.query(database.RepairJob).all()
    return [{
        "job_id": j.id,
        "name": j.name,
        "line": j.line,
        "track": j.track,
        "priority": j.priority,
        "status": j.status,
        "color": j.status_color,
        "scheduled_start": j.scheduled_start.isoformat() if j.scheduled_start else None,
        "scheduled_end": j.scheduled_end.isoformat() if j.scheduled_end else None,
        "assigned_engineers": [e.name for e in j.assigned_engineers]
    } for j in jobs]

@app.get("/alerts/", response_model=List[Dict[str, Any]])
def get_system_alerts(db: Session = Depends(get_db)):
    """Generates 15m/5m pre-start alerts and 1w/3d/1d deadline alerts."""
    now = datetime.datetime.now(datetime.timezone.utc)
    active_alerts = []
    jobs = db.query(database.RepairJob).filter(database.RepairJob.status != "Done").all()

    for j in jobs:
        if j.deadline:
            days_left = (j.deadline - now).days
            if days_left <= 1:
                active_alerts.append({"job_id": j.id, "type": "1day_deadline", "message": f"URGENT: Job '{j.name}' deadline is within 1 day!", "target": "Engineers"})
            elif days_left <= 3:
                active_alerts.append({"job_id": j.id, "type": "3days_deadline", "message": f"WARNING: Job '{j.name}' deadline is in 3 days.", "target": "Engineers"})
            elif days_left <= 7:
                active_alerts.append({"job_id": j.id, "type": "1week_deadline", "message": f"NOTICE: Job '{j.name}' deadline is in 1 week.", "target": "Engineers"})

        if j.scheduled_start:
            mins_to_start = int((j.scheduled_start - now).total_seconds() / 60)
            if 0 <= mins_to_start <= 5:
                active_alerts.append({"job_id": j.id, "type": "5min_before", "message": f"IMMINENT: Job '{j.name}' starts in 5 minutes!", "target": "Engineers & Management"})
            elif 5 < mins_to_start <= 15:
                active_alerts.append({"job_id": j.id, "type": "15min_before", "message": f"PREPARATION: Job '{j.name}' starts in 15 minutes.", "target": "Engineers & Management"})

    return active_alerts

@app.get("/audit-logs/", response_model=List[Dict[str, Any]])
def get_audit_logs(db: Session = Depends(get_db)):
    """Returns historical audit records."""
    logs = db.query(database.AuditLog).order_by(database.AuditLog.timestamp.desc()).all()
    return [{"id": l.id, "timestamp": l.timestamp.isoformat(), "action": l.action, "details": l.details, "approved_by": l.approved_by} for l in logs]
