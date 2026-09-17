import sqlite3
import json
from datetime import datetime
import uuid

DB_PATH = "database/audit_store.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            action_type TEXT NOT NULL,
            activity_id TEXT NOT NULL,
            author TEXT NOT NULL,
            changes TEXT NOT NULL,
            replan_triggered INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def record_audit(action_type: str, activity_id: str, author: str, changes: dict, replan_triggered: bool):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    log_id = f"LOG-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO audit_logs (log_id, timestamp, action_type, activity_id, author, changes, replan_triggered)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (log_id, timestamp, action_type, activity_id, author, json.dumps(changes), 1 if replan_triggered else 0))
    
    conn.commit()
    conn.close()
    return log_id

def get_all_audit_logs():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT log_id, timestamp, action_type, activity_id, author, changes, replan_triggered FROM audit_logs ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    
    logs = []
    for r in rows:
        logs.append({
            "log_id": r[0],
            "timestamp": r[1],
            "action_type": r[2],
            "activity_id": r[3],
            "author": r[4],
            "changes": json.loads(r[5]),
            "replan_triggered": bool(r[6])
        })
    return logs
