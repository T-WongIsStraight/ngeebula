# database.py
import datetime
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
    specialized_line = Column(String)
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
    deadline = Column(DateTime)
    
    priority = Column(String, default="Medium")      # Urgent, High, Medium, Low
    effort_level = Column(Integer, default=3)         # 1 to 5 scale
    duration_mins = Column(Integer, default=60)
    required_skill = Column(String, nullable=True)
    engineers_needed = Column(Integer, default=2)

    # Status & Colors: "Not started" (Black), "In progress" (Blue), "Delay" (Orange), "Error" (Red), "Done" (Green)
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
