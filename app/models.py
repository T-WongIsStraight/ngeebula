from pydantic import BaseModel
from typing import Dict, Any

class AuditEntry(BaseModel):
    log_id: str
    timestamp: str
    action_type: str
    activity_id: str
    author: str
    changes: Dict[str, Any]
    replan_triggered: bool
