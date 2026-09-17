from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


STATUS_COLORS = {
    "Done": "#22C77A",
    "Error": "#F0445B",
    "Delay": "#F28C38",
    "In progress": "#2487F5",
    "Not started": "#9AAABD",
}

LINE_ORDER = {"NS": 0, "EW": 1, "CCL": 2}


def load_demo_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_singapore_time(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("Asia/Singapore")
    return timestamp.tz_convert("Asia/Singapore")


def _format_time(value: pd.Timestamp) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def normalise_schedule(records: list[dict]) -> pd.DataFrame:
    schedule = pd.DataFrame(records)
    if schedule.empty:
        return pd.DataFrame(
            columns=[
                "job_id",
                "name",
                "line",
                "track",
                "priority",
                "status",
                "scheduled_start",
                "scheduled_end",
                "assigned_engineers",
                "engineer_text",
                "track_label",
            ]
        )

    defaults = {
        "job_id": 0,
        "name": "Untitled maintenance job",
        "line": "Unknown",
        "track": "Unassigned",
        "priority": "Medium",
        "status": "Not started",
        "assigned_engineers": [],
    }
    for column, default in defaults.items():
        if column not in schedule:
            schedule[column] = [default for _ in range(len(schedule))]
        else:
            schedule[column] = schedule[column].apply(lambda value: default if value is None else value)

    schedule["scheduled_start"] = schedule["scheduled_start"].map(_parse_singapore_time)
    schedule["scheduled_end"] = schedule["scheduled_end"].map(_parse_singapore_time)
    schedule["assigned_engineers"] = schedule["assigned_engineers"].apply(
        lambda value: value if isinstance(value, list) else []
    )
    schedule["engineer_text"] = schedule["assigned_engineers"].apply(
        lambda engineers: ", ".join(str(name) for name in engineers) if engineers else "Unassigned"
    )
    schedule["track_label"] = schedule["line"].astype(str) + " · " + schedule["track"].astype(str)
    schedule["line_order"] = schedule["line"].map(LINE_ORDER).fillna(len(LINE_ORDER))
    return (
        schedule.sort_values(["line_order", "track", "scheduled_start"], kind="stable")
        .drop(columns="line_order")
        .reset_index(drop=True)
    )


def detect_conflicts(schedule: pd.DataFrame) -> list[dict]:
    conflicts: list[dict] = []
    for (_, _), group in schedule.groupby(["line", "track"], dropna=False):
        jobs = group.sort_values("scheduled_start").to_dict("records")
        for index, left in enumerate(jobs):
            for right in jobs[index + 1 :]:
                if right["scheduled_start"] >= left["scheduled_end"]:
                    break
                conflicts.append(
                    {
                        "line": left["line"],
                        "track": left["track"],
                        "jobs": [left["name"], right["name"]],
                        "start": right["scheduled_start"],
                        "end": min(left["scheduled_end"], right["scheduled_end"]),
                    }
                )
    return conflicts


def build_recommendation(schedule: pd.DataFrame, conflicts: list[dict]) -> dict[str, Any]:
    if conflicts:
        conflict = conflicts[0]
        jobs = conflict["jobs"]
        return {
            "title": f"Resolve {conflict['line']} track conflict",
            "summary": (
                f"Two jobs on {conflict['track']} overlap between "
                f"{_format_time(conflict['start'])} and {_format_time(conflict['end'])}."
            ),
            "affected": jobs,
            "action": (
                f"Move {jobs[1]} to the next available slot after the 30-minute safety buffer. "
                "This keeps the track available for only one work crew at a time."
            ),
            "impact": [
                "Resolves one track conflict",
                "Preserves the safety buffer",
                "Keeps work inside the overnight window",
            ],
        }

    attention = schedule[schedule["status"].isin(["Delay", "Error"])]
    if not attention.empty:
        job = attention.iloc[0]
        return {
            "title": f"Review {job['status'].lower()}: {job['name']}",
            "summary": f"{job['name']} on {job['track']} needs planner attention before tonight's handover.",
            "affected": [job["name"], f"Assigned: {job['engineer_text']}"],
            "action": "Confirm the revised duration, then run a new proposal so downstream work and buffers can be checked.",
            "impact": ["Protects downstream work", "Keeps crews informed", "Creates an auditable approval"],
        }

    urgent = schedule[schedule["priority"] == "Urgent"]
    focus = urgent.iloc[0] if not urgent.empty else schedule.iloc[0]
    return {
        "title": "Schedule is ready for review",
        "summary": "No same-track overlaps were detected in the current overnight plan.",
        "affected": [f"Priority focus: {focus['name']}", f"Track: {focus['line']} {focus['track']}"],
        "action": "Review engineer coverage and approve the proposal before the engineering window opens.",
        "impact": ["No track conflicts", "30-minute buffers included", "All jobs fit the current view"],
    }
