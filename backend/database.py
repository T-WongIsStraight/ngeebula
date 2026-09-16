# database.py
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Table
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import datetime

SQLALCHEMY_DATABASE_URL = "sqlite:///./mrt_maintenance.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

engineer_skills = Table(
    'engineer_skills',
    Base.metadata,
    Column('engineer_id', Integer, ForeignKey('engineers.id'), primary_key=True),
    Column('skill_name', String, primary_key=True)
)

class Engineer(Base):
    __tablename__ = "engineers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    contact_no = Column(String)
    work_email = Column(String, unique=True)
    years_of_experience = Column(Integer)
    job_role = Column(String)
    specialized_line = Column(String)
    is_available = Column(Integer, default=1)

class RepairJob(Base):
    __tablename__ = "repair_jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    line = Column(String)
    track = Column(String)
    deadline = Column(DateTime)
    priority = Column(String)
    effort_level = Column(Integer)
    status = Column(String, default="Not started")
    assigned_engineers = Column(String, nullable=True)
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    action = Column(String)
    details = Column(String)
    approved_by = Column(String)

def init_db():
    Base.metadata.create_all(bind=engine)
