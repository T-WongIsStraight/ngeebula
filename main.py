# main.py
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import datetime
from typing import List, Optional, Dict, Any
from google import genai

import database
import solver

database.init_db()

app = FastAPI(title="SMRT Maintenance Backend", version="2.1")
client = genai.Client()

class JobCreate(BaseModel):
    name: str
    description: str
    line: str
    track: str
    deadline: datetime.datetime
    priority: str
    effort_level: int

class ChecklistUpdate(BaseModel):
    status: str
    reason: Optional[str] = None

class ApprovalPayload(BaseModel):
    approved: bool
    approved_by: str

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/jobs/", response_model=Dict[str, Any])
def create_repair_job(job: JobCreate, db: Session = Depends(get_db)):
    db_job = database.RepairJob(
        name=job.name,
        description=job.description,
        line=job.line,
        track=job.track,
        deadline=job.deadline,
        priority=job.priority,
        effort_level=job.effort_level,
        status="Not started"
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return {"status": "success", "message": "Job created successfully", "job_id": db_job.id}

@app.post("/schedule/run", response_model=Dict[str, Any])
def trigger_solver_and_gemini(db: Session = Depends(get_db)):
    jobs_db = db.query(database.RepairJob).filter(database.RepairJob.status != "Done").all()
    engineers_db = db.query(database.Engineer).all()
    
    jobs_data = [{
        "id": j.id,
        "name": j.name,
        "line": j.line,
        "track": j.track,
        "effort_level": j.effort_level,
        "priority": j.priority
    } for j in jobs_db]
    
    engineers_data = [{
        "id": e.id,
        "years_of_experience": e.years_of_experience,
        "specialized_line": e.specialized_line,
        "is_available": e.is_available
    } for e in engineers_db]
    
    schedule_results = solver.solve_mrt_schedule(jobs_data, engineers_data)
    
    if not schedule_results:
        raise HTTPException(status_code=400, detail="Solver could not find a valid feasible schedule.")
        
    base_time = datetime.datetime.utcnow()
    packaged_schedule = []
    
    for res in schedule_results:
        job = db.query(database.RepairJob).filter(database.RepairJob.id == res["id"]).first()
        if job:
            start_dt = base_time + datetime.timedelta(minutes=res["scheduled_start_min"])
            end_dt = base_time + datetime.timedelta(minutes=res["scheduled_end_min"])
            job.scheduled_start = start_dt
            job.scheduled_end = end_dt
            
            packaged_schedule.append({
                "job_id": job.id,
                "name": job.name,
                "line": job.line,
                "track": job.track,
                "priority": job.priority,
                "scheduled_start": start_dt.isoformat(),
                "scheduled_end": end_dt.isoformat()
            })
    db.commit()
    
    gemini_explanation = "Schedule compiled successfully."
    try:
        prompt = f"""
        You are an expert SMRT maintenance coordinator assistant. 
        Here is the newly calculated maintenance schedule:
        {packaged_schedule}
        
        Provide a short, professional, plain-English summary of this schedule, highlighting order of precedence, prioritized urgent jobs, and any key takeaways for management.
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        if response and response.text:
            gemini_explanation = response.text
    except Exception as e:
        gemini_explanation = f"Schedule generated, but AI narrative generation failed: {str(e)}"
        
    return {
        "status": "success",
        "schedule": packaged_schedule,
        "ai_explanation": gemini_explanation
    }

@app.patch("/checklist/{job_id}", response_model=Dict[str, Any])
def update_checklist(job_id: int, payload: ChecklistUpdate, db: Session = Depends(get_db)):
    job = db.query(database.RepairJob).filter(database.RepairJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job.status = payload.status
    db.commit()
    return {"status": "success", "message": f"Job {job_id} status updated to {payload.status}"}

@app.post("/approval/{job_id}", response_model=Dict[str, Any])
def process_approval(job_id: int, payload: ApprovalPayload, db: Session = Depends(get_db)):
    job = db.query(database.RepairJob).filter(database.RepairJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    action_type = "Approved" if payload.approved else "Rejected/Overridden"
    log = database.AuditLog(
        action=action_type,
        details=f"Schedule adjustment for job {job_id} ({job.name}) {action_type.lower()} by {payload.approved_by}",
        approved_by=payload.approved_by
    )
    db.add(log)
    db.commit()
    
    return {"status": "recorded", "action": action_type}
