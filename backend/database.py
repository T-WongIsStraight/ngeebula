# database.py
import datetime
import json
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Table, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

SQLALCHEMY_DATABASE_URL = "sqlite:///./smrt_maintenance.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Junction Table: Job <-> Engineer
job_engineers = Table(
    'job_engineers',
    Base.metadata,
    Column('job_id', Integer, ForeignKey('repair_jobs.id'), primary_key=True),
    Column('engineer_id', Integer, ForeignKey('engineers.id'), primary_key=True)
)

class Engineer(Base):
    __tablename__ = "engineers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    contact_no = Column(String)
    work_email = Column(String, unique=True)
    years_of_experience = Column(Integer, default=1)
    job_role = Column(String)
    specialized_lines = Column(Text)  # Stored as JSON string list
    is_available = Column(Boolean, default=True)

    skills = relationship("EngineerSkill", back_populates="engineer", cascade="all, delete-orphan")
    jobs = relationship("RepairJob", secondary=job_engineers, back_populates="assigned_engineers")

class EngineerSkill(Base):
    __tablename__ = "engineer_skills"

    id = Column(Integer, primary_key=True, index=True)
    engineer_id = Column(Integer, ForeignKey('engineers.id'))
    skill_name = Column(String, index=True)

    engineer = relationship("Engineer", back_populates="skills")

class RepairJob(Base):
    __tablename__ = "repair_jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    line = Column(String, index=True)
    track = Column(String, index=True)
    station_code = Column(String, nullable=True)
    is_interchange = Column(Boolean, default=False)
    deadline = Column(DateTime)
    
    category = Column(String, nullable=True)          # Matched from maintenance_db.json
    activity_type = Column(String, nullable=True)     # Preventive / Corrective
    priority = Column(String, default="Medium")       # Urgent, High, Medium, Low
    effort_level = Column(Integer, default=3)         # 1 to 5 scale
    duration_mins = Column(Integer, default=60)
    required_skills = Column(Text, nullable=True)     # JSON string list
    engineers_needed = Column(Integer, default=2)

    # Status & Color Mapping: "Not started" (Black), "In progress" (Blue), "Delay" (Orange), "Error" (Red), "Done" (Green)
    status = Column(String, default="Not started")
    status_color = Column(String, default="Black")
    is_approved = Column(Boolean, default=False)

    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)
    scheduled_start_min = Column(Integer, nullable=True)
    scheduled_end_min = Column(Integer, nullable=True)

    delay_reason = Column(Text, nullable=True)
    error_reason = Column(Text, nullable=True)
    ai_suggested_action = Column(Text, nullable=True)

    assigned_engineers = relationship("Engineer", secondary=job_engineers, back_populates="jobs")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    action = Column(String)
    details = Column(Text)
    approved_by = Column(String)

def init_db():
    Base.metadata.create_all(bind=engine)
    seed_engineers_if_empty()

def seed_engineers_if_empty():
    db = SessionLocal()
    try:
        if db.query(Engineer).count() == 0 and os.path.exists("engineer_db.json"):
            with open("engineer_db.json", "r") as f:
                data = json.load(f)
                engineers_data = data.get("engineers_db", [])
                for eng in engineers_data:
                    engineer = Engineer(
                        name=eng["name"],
                        work_email=eng.get("work_email"),
                        contact_no=eng.get("contact_no"),
                        years_of_experience=eng.get("years of experience", 1),
                        job_role=eng.get("roles/job scope"),
                        specialized_lines=json.dumps(eng.get("line_specialization", [])),
                        is_available=(eng.get("availability") == "Available")
                    )
                    db.add(engineer)
                    db.flush()
                    
                    for skill in eng.get("skillset", []):
                        db.add(EngineerSkill(engineer_id=engineer.id, skill_name=skill))
                db.commit()
    except Exception as e:
        db.rollback()
        print(f"Failed to seed engineer database: {e}")
    finally:
        db.close()
