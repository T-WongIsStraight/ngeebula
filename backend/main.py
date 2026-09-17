#main.py
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import datetime
import json
import os
from typing import List, Optional, Dict, Any
from google import genai

import database
import solver

database.init_db()

app = FastAPI(title="SMRT Railway Maintenance Backend API", version="4.0")

# --- On-Demand Gemini Client Helper ---
def get_gemini_client():
    """Instantiates client on-demand to prevent async cleanup crashes on startup."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"Gemini client initialization error: {e}")
        return None

STATUS_COLORS = {
    "Done": "Green",
    "Error": "Red",
    "Delay": "Orange",
    "In progress": "Blue",
    "Not started": "Black"
}

# --- JSON Database Loaders ---
def load_json_db(file_name: str) -> Dict[str, Any]:
    if os.path.exists(file_name):
        with open(file_name, "r") as f:
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

def minutes_to_datetime(min_offset: int) -> datetime.datetime:
    now = datetime.datetime.now(datetime.timezone.utc)
    base_window_start = now.replace(hour=0, minute=30, second=0, microsecond=0)
    if now.hour >= 5:
        base_window_start += datetime.timedelta(days=1)
    return base_window_start + datetime.timedelta(minutes=min_offset)

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
    2. Uses Gemini (with fallback) to compare against maintenance_db.json and derive priority/effort/skills.
    3. Reads engineers_db.json / SQL DB to select engineers using precedence rules.
    """
    station_code, is_interchange = match_station_info(job_in.line, job_in.track)
    now = datetime.datetime.now(datetime.timezone.utc)
    days_to_deadline = (job_in.deadline - now).days

    ai_eval = None
    client = get_gemini_client()

    if client:
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

        try:
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            cleaned = response.text.strip().lstrip("```json").rstrip("```").strip()
            ai_eval = json.loads(cleaned)
        except Exception as e:
            print(f"Gemini evaluation failed: {e}")
            ai_eval = None

    # Safe fallback if Gemini client is unavailable or call fails
    if not ai_eval:
        ai_eval = {
            "matched_category": "track_and_permanent_way",
            "activity_type": "Corrective",
            "required_skills": ["Track maintenance"],
            "priority": "High" if (is_interchange or days_to_deadline <= 7) else "Medium",
            "effort_level": 3,
            "duration_mins": 60,
            "engineers_needed": 3 if is_interchange else 2
        }

    # Select engineers using precedence order: Skillset match -> Line specialization -> Experience -> Availability
    req_skills = [s.lower() for s in ai_eval.get("required_skills", [])]
    needed_count = ai_eval.get("engineers_needed", 2)
    
    available_engineers = db.query(database.Engineer).filter(database.Engineer.is_available == True).all()
    candidate_scores = []
    
    for eng in available_engineers:
        eng_skills = [s.skill_name.lower() for s in eng.skills]
        spec_lines = json.loads(eng.specialized_lines or "[]")
        
        score = 0
        skill_matches = sum(1 for rs in req_skills if any(rs in es for es in eng_skills))
        score += skill_matches * 100
        
        if any(job_in.line.lower() in sl.lower() for sl in spec_lines):
            score += 25
            
        score += eng.years_of_experience
        candidate_scores.append((score, eng))
        
    candidate_scores.sort(key=lambda x: x[0], reverse=True)
    assigned_eng_objects = [item[1] for item in candidate_scores[:needed_count]]

    # Store in database
    db_job = database.RepairJob(
        name=job_in.name,
        description=job_in.description,
        line=job_in.line,
        track=job_in.track,
        station_code=station_code,
        is_interchange=is_interchange,
        deadline=job_in.deadline,
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

@app.post("/schedule/propose", response_model=Dict[str, Any])
def propose_schedule_options(db: Session = Depends(get_db)):
    """Fetches DB state, passes data to solver module, returns 3 scheduling options."""
    jobs_db = db.query(database.RepairJob).filter(database.RepairJob.status != "Done").all()
    engineers_db = db.query(database.Engineer).all()

    jobs_data = [{
        "id": j.id,
        "line": j.line,
        "track": j.track,
        "duration_mins": j.duration_mins,
        "priority": j.priority,
        "engineers_needed": j.engineers_needed
    } for j in jobs_db]

    engineers_data = [{
        "id": e.id,
        "name": e.name,
        "years_of_experience": e.years_of_experience,
        "is_available": e.is_available,
        "skills": [s.skill_name for s in e.skills]
    } for e in engineers_db]

    schedule_results = solver.solve_mrt_schedule(jobs_data, engineers_data)

    if not schedule_results:
        raise HTTPException(status_code=400, detail="Solver could not find a feasible non-overlapping schedule.")

    base_schedule = []
    for res in schedule_results:
        job = db.query(database.RepairJob).filter(database.RepairJob.id == res["id"]).first()
        if job:
            start_dt = minutes_to_datetime(res["scheduled_start_min"])
            end_dt = minutes_to_datetime(res["scheduled_end_min"])
            job.scheduled_start_min = res["scheduled_start_min"]
            job.scheduled_end_min = res["scheduled_end_min"]
            job.scheduled_start = start_dt
            job.scheduled_end = end_dt
            
            base_schedule.append({
                "job_id": job.id,
                "name": job.name,
                "line": job.line,
                "track": job.track,
                "station_code": job.station_code,
                "priority": job.priority,
                "scheduled_start": start_dt.isoformat(),
                "scheduled_end": end_dt.isoformat(),
                "assigned_engineers": [e.name for e in job.assigned_engineers]
            })
    db.commit()

    options = None
    client = get_gemini_client()

    if client:
        prompt = f"Baseline schedule: {json.dumps(base_schedule)}. Output 3 options in JSON: Option 1: Optimal, Option 2: Priority-Focused, Option 3: Balanced Workload."
        try:
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            cleaned = response.text.strip().lstrip("```json").rstrip("```").strip()
            options = json.loads(cleaned)
        except Exception as e:
            print(f"Gemini proposal error: {e}")

    if not options:
        options = [{"option_name": "Option 1: Recommended Schedule", "schedule": base_schedule}]

    return {"status": "success", "options": options, "base_schedule": base_schedule}

@app.post("/approval/{job_id}", response_model=Dict[str, Any])
def approve_or_override_job(job_id: int, payload: ApprovalPayload, db: Session = Depends(get_db)):
    """Handles higher-up approval and manual overrides, writing to AuditLog."""
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
    """Updates job status, handles engineer availability, and triggers AI re-scheduling on Delay or Error."""
    job = db.query(database.RepairJob).filter(database.RepairJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    new_status = payload.status
    if new_status not in STATUS_COLORS:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {list(STATUS_COLORS.keys())}")

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
            
        client = get_gemini_client()
        if client:
            prompt = f"Repair Job '{job.name}' updated to {new_status}. Reason: '{payload.reason}'. Suggest next course of action and schedule shift."
            try:
                res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                ai_action_summary = res.text if res else None
            except Exception as e:
                print(f"Gemini checklist suggestion error: {e}")

        if not ai_action_summary:
            ai_action_summary = "AI recommends shifting task to the next available maintenance window."

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
