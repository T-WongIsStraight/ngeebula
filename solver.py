"""Rail maintenance scheduler using OR-Tools."""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ortools.sat.python import cp_model


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Timestamps must be ISO strings with a timezone.")

    result = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if result.tzinfo is None:
        raise ValueError(
            "Timestamps must include Z or an offset such as +08:00."
        )

    if result.second or result.microsecond:
        raise ValueError(
            "Use whole-minute timestamps; seconds must be zero."
        )

    return result.astimezone(timezone.utc)


def skills(value):
    if not isinstance(value, list) or not all(
        isinstance(x, str) and x.strip() for x in value
    ):
        raise ValueError("Skills must be a list of nonempty strings.")

    return {x.strip().casefold() for x in value}


def run_solver(
    jobs,
    window_start=None,
    window_end=None,
    engineers=None,
    blocked_sectors=None,
    time_limit_seconds=10,
):
    """
    Return a JSON-compatible scheduling result.

    Explicit maintenance-window timestamps are required.

    Without engineers:
        Returns a track-only draft.

    With engineers:
        Requires required_skills and engineers_required on jobs.
        Requires skillset, available_start, available_end, and a unique
        id or work_email on engineers.

    Each assigned engineer must have ALL the job's required skills.
    All supplied jobs are mandatory; none are silently dropped.
    """
    warnings = []
    conflicts = []

    def fail(status, message):
        return {
            "status": status,
            "schedule": [],
            "ai_explanation": message,
            "conflicts": conflicts,
            "warnings": warnings,
        }

    try:
        if not isinstance(jobs, list):
            raise ValueError("jobs must be a list.")

        if not jobs:
            return {
                "status": "success",
                "schedule": [],
                "ai_explanation": "No jobs supplied.",
                "conflicts": [],
                "warnings": [],
            }

        if window_start is None or window_end is None:
            raise ValueError(
                "Supply window_start and window_end; "
                "no operating window is assumed."
            )

        base = timestamp(window_start)
        finish = timestamp(window_end)
        horizon = int((finish - base).total_seconds() / 60)

        if not 0 < horizon <= 31 * 24 * 60:
            raise ValueError(
                "Window must be positive and at most 31 days for this demo."
            )

        if (
            isinstance(time_limit_seconds, bool)
            or not 0 < time_limit_seconds <= 300
        ):
            raise ValueError(
                "Time limit must be greater than 0 and at most 300 seconds."
            )

        def minute(value):
            return int(
                (timestamp(value) - base).total_seconds() / 60
            )

        def iso(value):
            return (
                base + timedelta(minutes=value)
            ).isoformat()

        def sector(item):
            # Without a sector field, the entire line/track is exclusive.
            return (
                str(item["line"]).strip().casefold(),
                str(item["track"]).strip().casefold(),
                str(item.get("sector", "")).strip().casefold(),
            )

        records = []
        seen = set()

        for job in jobs:
            if not isinstance(job, dict):
                raise ValueError("Each job must be an object.")

            jid = job["id"]

            if (
                isinstance(jid, bool)
                or not isinstance(jid, (int, str))
                or str(jid) in seen
            ):
                raise ValueError(
                    "Job IDs must be unique integers or strings."
                )

            seen.add(str(jid))

            for key in ("name", "line", "track"):
                if (
                    not isinstance(job[key], str)
                    or not job[key].strip()
                ):
                    raise ValueError(
                        f"Job {jid}: {key} must be nonempty text."
                    )

            if (
                job.get("status", "Not started").casefold()
                != "not started"
            ):
                raise ValueError(
                    f"Job {jid}: only Not started jobs are supported; "
                    "do not move active/completed work."
                )

            original = minute(job["scheduled_start"])
            duration = minute(job["scheduled_end"]) - original

            if duration <= 0:
                raise ValueError(
                    f"Job {jid}: duration must be positive."
                )

            latest = min(horizon, minute(job["deadline"]))

            earliest = (
                max(0, minute(job["earliest_start"]))
                if job.get("earliest_start")
                else 0
            )

            priority = str(
                job.get("priority", "Medium")
            ).casefold()

            if priority not in ("high", "medium", "low"):
                raise ValueError(
                    f"Job {jid}: priority must be High, Medium, or Low."
                )

            if job.get("assigned_engineers"):
                raise ValueError(
                    "Existing engineer assignments must be modelled "
                    "as commitments; this demo accepts unassigned jobs only."
                )

            records.append(
                {
                    "job": job,
                    "id": jid,
                    "original": original,
                    "duration": duration,
                    "latest": latest,
                    "earliest": earliest,
                    "sector": sector(job),
                    "weight": {
                        "high": 3,
                        "medium": 2,
                        "low": 1,
                    }[priority],
                }
            )

        # Reject inconsistent location granularity.
        sectors = defaultdict(set)

        for record in records:
            sectors[record["sector"][:2]].add(
                record["sector"][2]
            )

        for block in blocked_sectors or []:
            block_sector = sector(block)
            sectors[block_sector[:2]].add(block_sector[2])

        if any(
            "" in values and len(values) > 1
            for values in sectors.values()
        ):
            raise ValueError(
                "Use consistent sector fields for all jobs/blocks "
                "on a line and track."
            )

        # Detect overlaps in the original requested schedule.
        for index, first in enumerate(records):
            for second in records[index + 1:]:
                same_location = (
                    first["sector"] == second["sector"]
                )

                overlap = max(
                    first["original"],
                    second["original"],
                ) < min(
                    first["original"] + first["duration"],
                    second["original"] + second["duration"],
                )

                if same_location and overlap:
                    conflicts.append(
                        {
                            "type": "original_track_overlap",
                            "job_ids": [
                                first["id"],
                                second["id"],
                            ],
                        }
                    )

        for record in records:
            available_minutes = (
                record["latest"] - record["earliest"]
            )

            if record["duration"] > available_minutes:
                return fail(
                    "infeasible",
                    f"Job {record['id']} cannot fit its "
                    "allowed window and deadline.",
                )

        model = cp_model.CpModel()

        track_intervals = defaultdict(list)
        engineer_intervals = defaultdict(list)
        staff = []

        if engineers is None:
            warnings.append(
                "TRACK-ONLY DRAFT: engineer skills, headcount "
                "and availability were not checked."
            )
        else:
            if isinstance(engineers, dict):
                engineers = engineers["engineers_db"]

            if not isinstance(engineers, list):
                raise ValueError(
                    "engineers must be a list or an engineers_db object."
                )

            engineer_ids = set()

            for engineer in engineers:
                engineer_id = engineer.get(
                    "id",
                    engineer.get("work_email"),
                )

                if (
                    engineer_id is None
                    or str(engineer_id) in engineer_ids
                ):
                    raise ValueError(
                        "Engineers need a unique id or work_email."
                    )

                engineer_ids.add(str(engineer_id))

                if (
                    "available_start" not in engineer
                    or "available_end" not in engineer
                ):
                    raise ValueError(
                        "Each engineer needs available_start and "
                        "available_end; Available/Busy labels are insufficient."
                    )

                available_start = minute(
                    engineer["available_start"]
                )
                available_end = minute(
                    engineer["available_end"]
                )

                if available_end <= available_start:
                    raise ValueError(
                        "Engineer availability end must follow start."
                    )

                if engineer.get("projects assigned"):
                    raise ValueError(
                        "Resolve existing projects assigned into "
                        "free availability before using engineer mode."
                    )

                staff.append(
                    (
                        engineer_id,
                        skills(engineer["skillset"]),
                        available_start,
                        available_end,
                    )
                )

        objective = []

        for record in records:
            label = str(record["id"])

            start = model.new_int_var(
                record["earliest"],
                record["latest"] - record["duration"],
                "start_" + label,
            )

            end = model.new_int_var(
                record["earliest"] + record["duration"],
                record["latest"],
                "end_" + label,
            )

            interval = model.new_interval_var(
                start,
                record["duration"],
                end,
                "job_" + label,
            )

            track_intervals[record["sector"]].append(interval)

            record.update(
                start=start,
                end=end,
                assignments=[],
            )

            maximum_change = max(
                abs(record["earliest"] - record["original"]),
                abs(
                    record["latest"]
                    - record["duration"]
                    - record["original"]
                ),
            )

            change = model.new_int_var(
                0,
                maximum_change,
                "change_" + label,
            )

            model.add_abs_equality(
                change,
                start - record["original"],
            )

            objective.append(record["weight"] * change)

            if engineers is not None:
                required = skills(
                    record["job"]["required_skills"]
                )
                count = record["job"]["engineers_required"]

                if (
                    not required
                    or type(count) is not int
                    or count < 1
                ):
                    raise ValueError(
                        "Jobs need nonempty required_skills and "
                        "positive integer engineers_required."
                    )

                for index, (
                    engineer_id,
                    known_skills,
                    available_start,
                    available_end,
                ) in enumerate(staff):
                    qualified = required <= known_skills

                    enough_time = (
                        min(available_end, record["latest"])
                        - max(available_start, record["earliest"])
                        >= record["duration"]
                    )

                    if qualified and enough_time:
                        chosen = model.new_bool_var(
                            f"assign_{label}_{index}"
                        )

                        model.add(
                            start >= available_start
                        ).only_enforce_if(chosen)

                        model.add(
                            end <= available_end
                        ).only_enforce_if(chosen)

                        optional_interval = (
                            model.new_optional_interval_var(
                                start,
                                record["duration"],
                                end,
                                chosen,
                                f"work_{label}_{index}",
                            )
                        )

                        engineer_intervals[
                            str(engineer_id)
                        ].append(optional_interval)

                        record["assignments"].append(
                            (engineer_id, chosen)
                        )

                if len(record["assignments"]) < count:
                    return fail(
                        "infeasible",
                        f"Job {record['id']} has too few fully "
                        "qualified engineers with sufficient availability.",
                    )

                model.add(
                    sum(
                        chosen
                        for _, chosen in record["assignments"]
                    )
                    == count
                )

        # Merge overlapping closure periods before adding them.
        closures = defaultdict(list)

        for block in blocked_sectors or []:
            lower = minute(block["start"])
            upper = minute(block["end"])

            if upper <= lower:
                raise ValueError(
                    "Sector closure end must follow start."
                )

            lower = max(0, lower)
            upper = min(horizon, upper)

            if upper > lower:
                closures[sector(block)].append(
                    (lower, upper)
                )

        for key, windows in closures.items():
            merged = []

            for lower, upper in sorted(windows):
                if merged and lower <= merged[-1][1]:
                    merged[-1] = (
                        merged[-1][0],
                        max(upper, merged[-1][1]),
                    )
                else:
                    merged.append((lower, upper))

            for index, (lower, upper) in enumerate(merged):
                closure = model.new_fixed_size_interval_var(
                    lower,
                    upper - lower,
                    f"closure_{key}_{index}",
                )
                track_intervals[key].append(closure)

        # A location or engineer cannot handle overlapping jobs.
        for intervals in (
            list(track_intervals.values())
            + list(engineer_intervals.values())
        ):
            model.add_no_overlap(intervals)

        # Higher priority means a stronger preference to preserve
        # the original start time. It does NOT mean "high first".
        model.minimize(sum(objective))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(
            time_limit_seconds
        )

        status = solver.solve(model)

        if status == cp_model.INFEASIBLE:
            return fail(
                "infeasible",
                "All jobs cannot fit together under the supplied "
                "constraints. Extend availability, add qualified staff, "
                "or explicitly defer jobs; none were silently dropped.",
            )

        if status == cp_model.MODEL_INVALID:
            return fail(
                "error",
                "Invalid optimisation model: " + model.validate(),
            )

        if status not in (
            cp_model.OPTIMAL,
            cp_model.FEASIBLE,
        ):
            return fail(
                "unknown",
                "Search ended without a schedule; "
                "this does not prove impossibility.",
            )

        schedule = []

        for record in records:
            job = record["job"]
            start_value = solver.value(record["start"])
            end_value = solver.value(record["end"])

            if engineers is not None:
                assigned = [
                    engineer_id
                    for engineer_id, chosen in record["assignments"]
                    if solver.value(chosen)
                ]
            else:
                assigned = None

            output = {
                "job_id": record["id"],
                "name": job["name"],
                "line": job["line"],
                "track": job["track"],
                "priority": job.get("priority", "Medium"),
                "status": job.get("status", "Not started"),
                "scheduled_start": iso(start_value),
                "scheduled_end": iso(end_value),
                "original_start": job["scheduled_start"],
                "shift_minutes": (
                    start_value - record["original"]
                ),
                "assigned_engineers": assigned,
            }

            if "sector" in job:
                output["sector"] = job["sector"]

            schedule.append(output)

        schedule.sort(
            key=lambda item: (
                item["scheduled_start"],
                str(item["job_id"]),
            )
        )

        moved = sum(
            item["shift_minutes"] != 0
            for item in schedule
        )

        explanation = (
            f"Scheduled {len(schedule)} jobs; moved {moved}. "
            "Same-location overlaps are prevented and deadlines respected. "
            "Objective: minimise priority-weighted changes "
            "from original start times. "
        )

        explanation += (
            "Engineer assignments checked."
            if engineers is not None
            else "Engineer feasibility NOT checked."
        )

        return {
            "status": "success",
            "solver_status": solver.status_name(status),
            "schedule": schedule,
            "engineers_checked": engineers is not None,
            "conflicts": conflicts,
            "warnings": warnings,
            "objective_value": solver.objective_value,
            "ai_explanation": explanation,
        }

    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return fail("error", f"Invalid input: {exc}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--jobs",
        default=str(Path(__file__).with_name("jobs.json")),
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("config.json")),
    )
    parser.add_argument(
        "--engineers",
        help="Optional engineer JSON with explicit shift times",
    )

    args = parser.parse_args()

    try:
        with open(args.jobs, encoding="utf-8") as file:
            jobs = json.load(file)

        with open(args.config, encoding="utf-8") as file:
            config = json.load(file)

        engineers = None

        if args.engineers:
            with open(args.engineers, encoding="utf-8") as file:
                engineers = json.load(file)

        result = run_solver(
            jobs,
            engineers=engineers,
            **config,
        )

    except (OSError, ValueError, TypeError) as exc:
        result = {
            "status": "error",
            "schedule": [],
            "ai_explanation": str(exc),
        }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
