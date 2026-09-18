"""The solve pipeline, with no web framework attached.

``run_pipeline`` is the whole job: read the 8 instance CSVs out of a folder,
run the solver, write the 3 submission CSVs, score the answer with our own
validator, and hand back the job body described in CLAUDE.md §8.2.

Both front doors use it:

* ``app.main`` (FastAPI) calls it on a worker thread, per uploaded job.
* ``streamlit_app`` calls it inline, on the folder it just wrote the uploads to.

Nothing in here touches HTTP, so it never raises ``HTTPException``. Every
failure comes back as a plain dict with a ``status`` the caller can show.
"""

from __future__ import annotations

import logging
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from app.explain import explain
from app.solver import load_instance, solve_schedule, write_submission
from app.validator import capacity_usage, horizon, table, validate

logger = logging.getLogger("ngeebula.pipeline")

#: solver status -> (job status, fallback message) when the solver returns no schedule
FAILURE_STATUS: Dict[str, tuple[str, str]] = {
    "INFEASIBLE": ("infeasible", "The rules cannot all be satisfied for this instance."),
    "UNKNOWN": ("timeout", "The solver ran out of time before it found a schedule."),
    "MODEL_INVALID": ("error", "The instance produced an invalid model."),
}

TIME_LIMIT_DEFAULT = 60.0
SOLVER_WORKERS = 1  # deterministic output; see CLAUDE.md §12


def instance_summary(instance: Mapping[str, Any]) -> Dict[str, Any]:
    """The instance echoed back as plain rows, for the screens that draw it."""
    horizon_start, horizon_weeks = horizon(instance)
    return {
        "horizon_start": horizon_start.isoformat(),
        "horizon_weeks": horizon_weeks,
        "contracts": table(instance, "project_details"),
        "activities": table(instance, "activity_details"),
        "locations": table(instance, "location_supply"),
        "sectors": table(instance, "sectors"),
    }


def join_results(
    instance: Mapping[str, Any], results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """RESULTS.csv rows plus the two contract columns every result screen needs."""
    projects = {
        str(row.get("contract_number", "")).strip(): row
        for row in table(instance, "project_details")
    }
    joined = []
    for row in results:
        contract = str(row.get("contract_number", "")).strip()
        project = projects.get(contract, {})
        merged = dict(row)
        merged["contract_priority"] = project.get("contract_priority")
        merged["planned_completion_date"] = project.get("planned_completion_date")
        joined.append(merged)
    return joined


def _outcome(
    *,
    status: str,
    message: str,
    solver_status: Optional[str],
    elapsed: float,
    result: Optional[Dict[str, Any]] = None,
    error_code: Optional[str] = None,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "status": status,
        "message": message,
        "solver_status": solver_status,
        "elapsed_s": elapsed,
    }
    if error_code:
        body["error_code"] = error_code
    if result is not None:
        body["result"] = result
    return body


def run_pipeline(
    instance_dir: str | Path,
    scenario: str,
    time_limit_seconds: float = TIME_LIMIT_DEFAULT,
    num_workers: int = SOLVER_WORKERS,
    out_dir: str | Path | None = None,
    label: str = "pipeline",
) -> Dict[str, Any]:
    """Solve one instance and return the job body.

    Args:
        instance_dir: folder holding the 8 instance CSVs, by their official names.
        scenario: ``"A"``, ``"B"`` or ``"C"``.
        time_limit_seconds: how long the solver may think.
        num_workers: solver threads; 1 keeps the answer deterministic.
        out_dir: where to write the 3 submission CSVs. ``None`` writes nothing.
        label: what to call this run in the log.

    Returns:
        ``{status, message, solver_status, elapsed_s}`` plus ``error_code`` on a
        failure and ``result`` (the CLAUDE.md §8.2 ``SolveResult``) on success.
        ``status`` is one of ``done``, ``infeasible``, ``timeout`` or ``error``.
    """
    started = time.time()
    folder = Path(instance_dir)
    try:
        instance = load_instance(folder)
        result = solve_schedule(
            instance,
            scenario=scenario,
            time_limit_seconds=time_limit_seconds,
            num_workers=num_workers,
        )
        solver_status = result.get("solver_status")
        if result.get("status") != "success":
            status, default_message = FAILURE_STATUS.get(
                str(solver_status), ("infeasible", "The solver did not return a schedule.")
            )
            return _outcome(
                status=status,
                message=result.get("message") or default_message,
                solver_status=solver_status,
                elapsed=time.time() - started,
            )

        access = [dict(r) for r in result.get("schedule_access", [])]
        occupancy = [dict(r) for r in result.get("schedule_occupancy", [])]
        results_rows = [dict(r) for r in result.get("results", [])]

        if out_dir is not None:
            write_submission(result, out_dir)

        report = validate(instance, access, occupancy, results_rows, scenario)
        usage = result.get("capacity_usage") or capacity_usage(instance, occupancy)
        metrics = result.get("metrics") or {}

        solve_result = {
            "scenario": scenario,
            "instance": instance_summary(instance),
            "schedule_access": access,
            "schedule_occupancy": occupancy,
            "results": join_results(instance, results_rows),
            "report": report,
            "capacity_usage": usage,
            "explanations": explain(instance, access, occupancy, results_rows),
            "metrics": {
                "wall_time_seconds": metrics.get("wall_time_seconds"),
                "solver_status": solver_status,
                "objective_value": result.get("objective_value"),
            },
            "warnings": list(result.get("warnings") or []),
        }
        return _outcome(
            status="done",
            message=(
                f"Scenario {scenario} scheduled. "
                f"{'No rule breaches found' if report['feasible'] else 'Rule breaches found'}; "
                f"score {report['soft_scores']['objective_score']}."
            ),
            solver_status=solver_status,
            elapsed=time.time() - started,
            result=solve_result,
        )
    except ValueError as exc:
        # bad instance data: the message is ours, so it is safe to show
        logger.warning("%s rejected the instance: %s", label, exc)
        return _outcome(
            status="error",
            message=f"The uploaded instance could not be used: {exc}",
            solver_status=None,
            elapsed=time.time() - started,
            error_code="BAD_INSTANCE",
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("%s crashed: %s\n%s", label, exc, traceback.format_exc())
        return _outcome(
            status="error",
            message="The scheduler hit an unexpected error. Please try again.",
            solver_status=None,
            elapsed=time.time() - started,
            error_code="SOLVE_FAILED",
        )
