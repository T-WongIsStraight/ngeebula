# main.py
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import datetime
import json
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from google import genai

try:
    from . import database, solver
except ImportError:
    import database
    import solver

database.init_db()

app = FastAPI(title="SMRT Railway Maintenance Backend API", version="4.0")
# Missing AI credentials must not prevent the server from starting.
client = None
try:
    client = genai.Client()
except Exception:
    pass

STATUS_COLORS = {
    "Done": "Green",
    "Error": "Red",
    "Delay": "Orange",
    "In progress": "Blue",
    "Not started": "Black"
}

# --- JSON Database Loaders ---
def load_json_db(file_name: str) -> Dict[str, Any]:
    path = Path(__file__).resolve().parent / file_name
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}

MAINTENANCE_DB = load_json_db("maintenance_db.json")
STATIONS_DB = load_json_db("stations_db.json")
ENGINEER_DB = load_json_db("engineers_db.json")

# --- Pydantic Request Schemas ---
class JobInput(BaseModel):
    name: str
    description: str
    line: str
    track: str
    deadline: datetime.datetime
    required_skills: Optional[List[str]] = None
    duration_mins: Optional[int] = None
    engineers_needed: Optional[int] = None
    priority: Optional[str] = None

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

# --- Helper Functions ---
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_color(status: str) -> str:
    return STATUS_COLORS.get(status, "Black")

def minutes_to_datetime(min_offset: int, window_start=None) -> datetime.datetime:
    start = solver.as_utc(window_start) if window_start else solver.next_window()[0]
    return start + datetime.timedelta(minutes=min_offset)


def utc(value):
    return solver.as_utc(value)


def iso_or_none(value):
    return utc(value).isoformat() if value else None


@app.get('/health')
def health():
    return {'status': 'ok', 'ai_available': client is not None}


def match_station_info(line_name: str, track_input: str) -> tuple[Optional[str], bool]:
    """Scans stations_db.json to find station code and interchange status."""
    all_networks = {**STATIONS_DB.get("MRT_Lines", {}), **STATIONS_DB.get("LRT_Networks", {})}
    
    matched_stations = []
    for line_key, stations in all_networks.items():
        if line_name.lower() in line_key.lower():
            for st in stations:
                if st["name"].lower() in track_input.lower() or st["code"].lower() in track_input.lower():
                    matched_stations.append(st)
                    
    if matched_stations:
        target = matched_stations[0]
        return target["code"], len(target.get("interchange", [])) > 0
    return None, False

# --- Endpoints ---

@app.post("/jobs/parse-and-create", response_model=Dict[str, Any])
def parse_job_and_create(job_in: JobInput, db: Session = Depends(get_db)):
    """
    1. Reads stations_db.json to assign station_code and check interchange status.
    2. Uses Gemini to compare against maintenance_db.json and derive priority/effort/skills.
    3. Reads engineers_db.json / SQL DB to select engineers using precedence rules.
    """
    station_code, is_interchange = match_station_info(job_in.line, job_in.track)
    now = datetime.datetime.now(datetime.timezone.utc)
    if job_in.deadline.tzinfo is None:
        raise HTTPException(422, 'deadline must include a timezone, e.g. +08:00')
    days_to_deadline = (utc(job_in.deadline) - now).days

    prompt = f"""
    You are an expert SMRT maintenance planner.
    
    Task Title: {job_in.name}
    Description: {job_in.description}
    Line: {job_in.line}
    Track/Station: {job_in.track} (Interchange: {is_interchange})
    Days until Deadline: {days_to_deadline} days
    
    Reference Maintenance Catalog JSON:
    {json.dumps(MAINTENANCE_DB.get("maintenance_catalog", {}), indent=2)}

    Evaluate the task and return strict JSON with these keys:
    - "matched_category": key of closest category in catalog.
    - "activity_type": "Preventive" or "Corrective"
    - "required_skills": list of required skill strings from the catalog.
    - "priority": one of ["Urgent", "High", "Medium", "Low"] adhering to rules:
        * Urgent: serious risk of breakdown, deadline < 7 days.
        * High: monthly maintenance, deadline 14-21 days, or high-load interchange station.
        * Medium: quarterly maintenance, deadline 30-60 days.
        * Low: yearly maintenance, deadline > 60 days.
    - "effort_level": integer 1 to 5 based on complexity.
    - "duration_mins": repair duration in minutes (30, 45, 60, 90, 120).
    - "engineers_needed": integer (2 to 5). Priority Urgent requires higher count.
    """

    manual = (job_in.required_skills is not None and job_in.duration_mins is not None
              and job_in.engineers_needed is not None and job_in.priority is not None)
    if manual:
        ai_eval = dict(required_skills=job_in.required_skills, duration_mins=job_in.duration_mins,
                       engineers_needed=job_in.engineers_needed, priority=job_in.priority, effort_level=3)
    else:
        if client is None:
            raise HTTPException(503, 'AI credentials unavailable. Configure the backend Gemini key or supply required_skills, duration_mins, engineers_needed and priority explicitly.')
        try:
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt,
                config={'response_mime_type': 'application/json'})
            ai_eval = json.loads(response.text)
        except Exception:
            raise HTTPException(502, 'Could not parse job requirements. Retry or supply explicit requirements; no default qualifications were invented.')
    if (not isinstance(ai_eval, dict)
        or not isinstance(ai_eval.get('required_skills'), list)
        or not ai_eval['required_skills']
        or not all(isinstance(x, str) and x.strip() for x in ai_eval['required_skills'])
        or type(ai_eval.get('duration_mins')) is not int or not 0 < ai_eval['duration_mins'] <= 300
        or type(ai_eval.get('engineers_needed')) is not int or not 0 < ai_eval['engineers_needed'] <= 700
        or ai_eval.get('priority') not in ['Urgent', 'High', 'Medium', 'Low']):
        raise HTTPException(422, 'Invalid skills, priority, duration or engineer count; review job requirements.')

    # Assign engineers jointly with timing in the solver, not by a greedy score.
    needed_count = ai_eval['engineers_needed']
    assigned_eng_objects = []

    # Store in database
    db_job = database.RepairJob(
        name=job_in.name,
        description=job_in.description,
        line=job_in.line,
        track=job_in.track,
        station_code=station_code,
        is_interchange=is_interchange,
        deadline=utc(job_in.deadline).replace(tzinfo=None),
        category=ai_eval.get("matched_category"),
        activity_type=ai_eval.get("activity_type"),
        priority=ai_eval.get("priority"),
        effort_level=ai_eval.get("effort_level"),
        duration_mins=ai_eval.get("duration_mins"),
        required_skills=json.dumps(ai_eval.get("required_skills", [])),
        engineers_needed=needed_count,
        status="Not started",
        status_color=get_color("Not started"),
        is_approved=False,
        assigned_engineers=assigned_eng_objects
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)

    return {
        "status": "success",
        "job_id": db_job.id,
        "station_code": station_code,
        "is_interchange": is_interchange,
        "ai_evaluation": ai_eval,
        "assigned_engineers": [{"id": e.id, "name": e.name, "role": e.job_role} for e in assigned_eng_objects]
    }

class ScheduleRequest(BaseModel):
    window_start: Optional[datetime.datetime] = None
    window_end: Optional[datetime.datetime] = None


@app.post('/schedule/propose', response_model=Dict[str, Any])
def propose_schedule_options(payload: Optional[ScheduleRequest] = None, db: Session = Depends(get_db)):
    jobs_db = db.query(database.RepairJob).filter(database.RepairJob.status != 'Done').all()
    if any(j.is_approved or j.status != 'Not started' for j in jobs_db):
        raise HTTPException(409, 'Active, delayed/error or approved work exists. This version will not silently move it; resolve those commitments before replanning.')
    if payload and (payload.window_start is not None or payload.window_end is not None):
        if not payload.window_start or not payload.window_end:
            raise HTTPException(422, 'Supply both window endpoints.')
        if payload.window_start.tzinfo is None or payload.window_end.tzinfo is None:
            raise HTTPException(422, 'Window timestamps must include a timezone.')
        start, end = utc(payload.window_start), utc(payload.window_end)
        local_start, local_end = start.astimezone(solver.SGT), end.astimezone(solver.SGT)
        if (local_start.time() != datetime.time(0, 30) or local_end.time() != datetime.time(5)
                or local_start.date() != local_end.date()):
            raise HTTPException(422, 'Window must be 00:30–05:00 on one Singapore date.')
        if start < datetime.datetime.now(datetime.timezone.utc):
            raise HTTPException(422, 'Choose a future maintenance window.')
    else:
        start, end = solver.next_window()
    jobs_data = [{k: getattr(j, k) for k in (
        'id','name','line','track','deadline','duration_mins','priority','required_skills',
        'engineers_needed','status','is_approved','scheduled_start')} for j in jobs_db]
    engineers_db = db.query(database.Engineer).all()
    engineers_data = [dict(id=e.id, is_available=e.is_available,
                          skills=[s.skill_name for s in e.skills]) for e in engineers_db]
    result = solver.solve_mrt_schedule(jobs_data, engineers_data, start, end)
    if result['status'] != 'success':
        code = 422 if result['status'] == 'error' else 409
        raise HTTPException(code, detail=result)
    by_id = {j.id: j for j in jobs_db}
    staff = {e.id: e for e in engineers_db}
    base_schedule = []
    for row in result['schedule']:
        j = by_id[row['id']]
        j.scheduled_start = utc(row['scheduled_start']).replace(tzinfo=None)
        j.scheduled_end = utc(row['scheduled_end']).replace(tzinfo=None)
        j.scheduled_start_min = row['scheduled_start_min']
        j.scheduled_end_min = row['scheduled_end_min']
        j.assigned_engineers = [staff[eid] for eid in row['assigned_engineers']]
        base_schedule.append(dict(row, station_code=j.station_code,
                                 assigned_engineer_ids=row['assigned_engineers'],
                                 assigned_engineers=[e.name for e in j.assigned_engineers]))
    db.add(database.AuditLog(action='Schedule proposed', details=result['ai_explanation'], approved_by='Solver'))
    db.commit()
    # Return one actually solved option. Do not fabricate alternatives via an LLM.
    return dict(result, base_schedule=base_schedule,
                options=[{'option_name':'Constraint-checked proposal', 'schedule':base_schedule}])


@app.post("/approval/{job_id}", response_model=Dict[str, Any])
def approve_or_override_job(job_id: int, payload: ApprovalPayload, db: Session = Depends(get_db)):
    """Handles higher-up approval and manual overrides, writing to AuditLog."""
    job = db.query(database.RepairJob).filter(database.RepairJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if any(value is not None for value in (payload.override_start_min, payload.override_priority, payload.override_engineers)):
        raise HTTPException(409, 'Manual overrides require a new constraint-checked proposal; direct overrides are disabled.')
    if payload.approved and (job.scheduled_start is None or job.scheduled_end is None):
        raise HTTPException(409, 'Generate a feasible schedule before approving this job.')
    action_text = 'Approved' if payload.approved else 'Rejected'
    job.is_approved = payload.approved

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
    """Updates job status, handles engineer availability, and triggers AI re-scheduling on Delay or Error."""
    job = db.query(database.RepairJob).filter(database.RepairJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    new_status = payload.status
    if new_status not in STATUS_COLORS:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {list(STATUS_COLORS.keys())}")

    if payload.updated_repair_time_mins is not None and not 0 < payload.updated_repair_time_mins <= 300:
        raise HTTPException(422, 'Repair duration must be 1–300 minutes.')
    job.status = new_status
    job.status_color = get_color(new_status)
    ai_action_summary = None

    if new_status == "Done":
        # Preserve assignment history. is_available is operator-supplied window availability.
        pass

    elif new_status in ("Delay", "Error"):
        if new_status == "Delay":
            job.delay_reason = payload.reason
            if payload.updated_repair_time_mins:
                job.duration_mins = payload.updated_repair_time_mins
        else:
            job.error_reason = payload.reason
            
        prompt = f"Repair Job '{job.name}' updated to {new_status}. Reason: '{payload.reason}'. Suggest next course of action and schedule shift."
        try:
            res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt) if client else None
            ai_action_summary = res.text if res else 'Planner review required; no automatic rescheduling has occurred.'
        except Exception:
            ai_action_summary = 'Planner review required; no automatic rescheduling has occurred.' 
        job.ai_suggested_action = ai_action_summary
        job.is_approved = False

    audit = database.AuditLog(
        action=f"Status -> {new_status}",
        details=f"Job {job_id} updated to {new_status} by {payload.updated_by}. Reason: {payload.reason or 'N/A'}",
        approved_by=payload.updated_by
    )
    db.add(audit)
    db.commit()

    return {
        "status": "success",
        "job_id": job_id,
        "new_status": new_status,
        "status_color": job.status_color,
        "ai_suggested_action": ai_action_summary
    }

@app.get("/dashboard/gantt", response_model=List[Dict[str, Any]])
def get_gantt_chart_data(db: Session = Depends(get_db)):
    """Returns color-coded Gantt chart data."""
    jobs = db.query(database.RepairJob).all()
    return [{
        "job_id": j.id,
        "name": j.name,
        "line": j.line,
        "track": j.track,
        "station_code": j.station_code,
        "is_interchange": j.is_interchange,
        "priority": j.priority,
        "status": j.status,
        "color": j.status_color,
        "scheduled_start": iso_or_none(j.scheduled_start),
        "scheduled_end": iso_or_none(j.scheduled_end),
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
            days_left = (utc(j.deadline) - now).days
            if days_left <= 1:
                active_alerts.append({"job_id": j.id, "type": "1day_deadline", "message": f"URGENT: Job '{j.name}' deadline is within 1 day!", "target": "Engineers"})
            elif days_left <= 3:
                active_alerts.append({"job_id": j.id, "type": "3days_deadline", "message": f"WARNING: Job '{j.name}' deadline is in 3 days.", "target": "Engineers"})
            elif days_left <= 7:
                active_alerts.append({"job_id": j.id, "type": "1week_deadline", "message": f"NOTICE: Job '{j.name}' deadline is in 1 week.", "target": "Engineers"})

        if j.scheduled_start:
            mins_to_start = int((utc(j.scheduled_start) - now).total_seconds() / 60)
            if 0 <= mins_to_start <= 5:
                active_alerts.append({"job_id": j.id, "type": "5min_before", "message": f"IMMINENT: Job '{j.name}' starts in 5 minutes!", "target": "Engineers & Management"})
            elif 5 < mins_to_start <= 15:
                active_alerts.append({"job_id": j.id, "type": "15min_before", "message": f"PREPARATION: Job '{j.name}' starts in 15 minutes.", "target": "Engineers & Management"})

    return active_alerts

@app.get("/audit-logs/", response_model=List[Dict[str, Any]])
def get_audit_logs(db: Session = Depends(get_db)):
    """Returns historical audit records."""
    logs = db.query(database.AuditLog).order_by(database.AuditLog.timestamp.desc()).all()
    return [{"id": l.id, "timestamp": iso_or_none(l.timestamp), "action": l.action, "details": l.details, "approved_by": l.approved_by} for l in logs]
