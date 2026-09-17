from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class TaskUpdateSchema(BaseModel):
    activity_id: str
    status: Optional[str] = None  # "Not Started", "In Progress", "Done"
    total_accesses: Optional[float] = None
    planned_start_date: Optional[str] = None
    author: str = "Works_Controller"

class TaskCreateSchema(BaseModel):
    activity_id: str
    contract_number: str
    activity_type: str  # PC, C, PM
    nature_of_works: str  # Live, Non-live (Consist), Non-live (Others)
    total_accesses: float
    start_location_id: str
    end_location_id: str
    planned_start_date: str
    activity_priority: int
    author: str = "Works_Controller"

class AuditEntry(BaseModel):
    log_id: str
    timestamp: str
    action_type: str
    activity_id: str
    author: str
    changes: Dict[str, Any]
    replan_triggered: bool
