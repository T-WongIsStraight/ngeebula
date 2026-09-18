"""NebulaX PS1 backend — FastAPI, contract v2 (CLAUDE.md §8.2).

Judges upload the 8 instance CSVs, pick a scenario, and poll a job until the
solver is done. Every response is JSON with a stable shape; nothing ever comes
back as a bare 500 with a stack trace in it.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import os
import shutil
import tempfile
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.pipeline import run_pipeline
from app.solver import load_instance
from app.validator import validate

VERSION = "2.0.0"

logger = logging.getLogger("ngeebula.api")

# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #

#: the 8 official instance files, by their canonical (upper-case) name
INSTANCE_FILES: Tuple[str, ...] = (
    "01_LINES.csv",
    "02_STATIONS.csv",
    "03_SECTORS.csv",
    "04_LOCATION_SUPPLY.csv",
    "05_BUFFER_LOCATION.csv",
    "06_PARAMETERS.csv",
    "07_PROJECT_DETAILS.csv",
    "08_ACTIVITY_DETAILS.csv",
)
#: the 3 submission files
SUBMISSION_FILES: Tuple[str, ...] = (
    "SCHEDULE_ACCESS.csv",
    "SCHEDULE_OCCUPANCY.csv",
    "RESULTS.csv",
)

_LOOKUP = {name.lower(): name for name in INSTANCE_FILES + SUBMISSION_FILES}

JOBS_ROOT = Path(
    os.getenv("JOBS_DIR") or (Path(__file__).resolve().parent.parent / "jobs")
)
JOB_TTL_SECONDS = 2 * 60 * 60
MAX_CONCURRENT_SOLVES = 2
TIME_LIMIT_MIN, TIME_LIMIT_MAX, TIME_LIMIT_DEFAULT = 5.0, 300.0, 60.0
SOLVER_WORKERS = 1  # deterministic output; see CLAUDE.md §12

app = FastAPI(title="NebulaX PS1 Railway Track Access API", version=VERSION)

# allow_credentials must be False when allow_origins is "*" — the browser
# rejects the combination and every preflight fails.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SOLVES, thread_name_prefix="solve")
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# errors
# --------------------------------------------------------------------------- #

def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error_code": code, "message": message})


@app.exception_handler(HTTPException)
async def _http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "error_code" in detail:
        body = detail
    else:
        body = {"error_code": "HTTP_ERROR", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled error: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL",
            "message": "The server hit an unexpected error. Nothing was changed; try again.",
        },
    )


# --------------------------------------------------------------------------- #
# upload handling
# --------------------------------------------------------------------------- #

async def _collect_uploads(request: Request, required: Tuple[str, ...]) -> Dict[str, bytes]:
    """Read a multipart body under any field names and key it by file name.

    Names are matched case-insensitively against the official list after
    ``os.path.basename``, so ``../evil.csv`` can never escape the job folder —
    it simply is not one of the names we accept, and the request is rejected
    before a single byte is written.
    """
    try:
        form = await request.form()
    except Exception as exc:  # malformed multipart
        raise _error(400, "BAD_MULTIPART", f"Could not read the upload: {exc}") from exc

    found: Dict[str, bytes] = {}
    unknown: List[str] = []
    # multi_items(), not values(): a browser <input multiple> sends every file
    # under the same field name, and values() would keep only the last one.
    for _field, value in form.multi_items():
        filename = getattr(value, "filename", None)
        if not filename:
            continue
        base = os.path.basename(str(filename).replace("\\", "/")).strip()
        canonical = _LOOKUP.get(base.lower())
        if canonical is None or canonical not in required:
            unknown.append(str(filename))
            continue
        found[canonical] = await value.read()

    missing = [name for name in required if name not in found]
    if missing or unknown:
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if unknown:
            parts.append("not accepted: " + ", ".join(sorted(set(unknown))[:10]))
        raise _error(
            400,
            "BAD_UPLOAD",
            "Upload exactly these files (any field name, name must match): "
            + ", ".join(required)
            + ". " + "; ".join(parts),
        )
    return found


def _write_files(folder: Path, files: Mapping[str, bytes]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, blob in files.items():
        # name comes from _LOOKUP, so it is one of the 11 constants above.
        (folder / name).write_bytes(blob)


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _scenario(raw: Any) -> str:
    value = str(raw or "").strip().upper()
    if value not in {"A", "B", "C"}:
        raise _error(400, "BAD_SCENARIO", "scenario must be one of A, B or C")
    return value


def _time_limit(raw: Any) -> float:
    if raw in (None, ""):
        return TIME_LIMIT_DEFAULT
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise _error(400, "BAD_TIME_LIMIT", "time_limit must be a number of seconds") from None
    return max(TIME_LIMIT_MIN, min(TIME_LIMIT_MAX, value))


# --------------------------------------------------------------------------- #
# job registry
# --------------------------------------------------------------------------- #

def _prune_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    with _jobs_lock:
        stale = [jid for jid, job in _jobs.items() if job["created"] < cutoff]
        folders = [_jobs.pop(jid)["folder"] for jid in stale]
    for folder in folders:
        shutil.rmtree(folder, ignore_errors=True)


def _new_job(scenario: str, time_limit: float) -> Dict[str, Any]:
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    folder = tempfile.mkdtemp(prefix=f"{job_id}_", dir=str(JOBS_ROOT))
    job = {
        "job_id": job_id,
        "folder": folder,
        "scenario": scenario,
        "time_limit": time_limit,
        "status": "running",
        "message": f"Scheduling scenario {scenario}…",
        "solver_status": None,
        "elapsed_s": 0.0,
        "created": time.time(),
        "started": time.time(),
        "result": None,
    }
    with _jobs_lock:
        _jobs[job_id] = job
    return job


def _get_job(job_id: str) -> Dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise _error(404, "JOB_NOT_FOUND", f"No job {job_id}. Jobs are kept for 2 hours.")
    return job


def _public_job(job: Dict[str, Any]) -> Dict[str, Any]:
    view = {
        "job_id": job["job_id"],
        "status": job["status"],
        "message": job["message"],
        "solver_status": job["solver_status"],
        "elapsed_s": round(
            job["elapsed_s"] if job["status"] != "running" else time.time() - job["started"], 2
        ),
    }
    if job.get("error_code"):
        view["error_code"] = job["error_code"]
    if job.get("result") is not None:
        view["result"] = job["result"]
    return view


# --------------------------------------------------------------------------- #
# the solve itself
# --------------------------------------------------------------------------- #

def _run_job(job: Dict[str, Any]) -> None:
    """Run one job's solve. All the work lives in ``app.pipeline``."""
    folder = Path(job["folder"])
    outcome = run_pipeline(
        folder,
        job["scenario"],
        time_limit_seconds=job["time_limit"],
        num_workers=SOLVER_WORKERS,
        out_dir=folder,          # the download endpoint serves the 3 CSVs from here
        label=f"job {job['job_id']}",
    )
    _finish(
        job,
        status=outcome["status"],
        message=outcome["message"],
        solver_status=outcome["solver_status"],
        elapsed=outcome["elapsed_s"],
        result=outcome.get("result"),
        error_code=outcome.get("error_code"),
    )


def _finish(
    job: Dict[str, Any],
    *,
    status: str,
    message: str,
    solver_status: Optional[str],
    elapsed: float,
    result: Optional[Dict[str, Any]] = None,
    error_code: Optional[str] = None,
) -> None:
    with _jobs_lock:
        job["status"] = status
        job["message"] = message
        job["solver_status"] = solver_status
        job["elapsed_s"] = elapsed
        job["result"] = result
        if error_code:
            job["error_code"] = error_code


# --------------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------------- #

@app.get("/api/health")
def health() -> Dict[str, Any]:
    with _jobs_lock:
        running = sum(1 for job in _jobs.values() if job["status"] == "running")
    return {"ok": True, "version": VERSION, "jobs_running": running}


@app.post("/api/solve")
async def solve(request: Request, wait: bool = False) -> JSONResponse:
    """Start a solve. Returns 202 {job_id}; ``?wait=true`` blocks and returns the job."""
    _prune_jobs()
    form = await request.form()
    scenario = _scenario(form.get("scenario"))
    time_limit = _time_limit(form.get("time_limit"))
    files = await _collect_uploads(request, INSTANCE_FILES)

    job = _new_job(scenario, time_limit)
    _write_files(Path(job["folder"]), files)
    future = _executor.submit(_run_job, job)

    if wait:
        # Await the thread without blocking the event loop, so /api/health and
        # other jobs' polling keep answering while this solve runs.
        await asyncio.wrap_future(future)
        return JSONResponse(status_code=200, content=_public_job(_get_job(job["job_id"])))
    return JSONResponse(status_code=202, content={"job_id": job["job_id"]})


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> Dict[str, Any]:
    return _public_job(_get_job(job_id))


@app.get("/api/jobs/{job_id}/download/{filename}")
def download(job_id: str, filename: str) -> FileResponse:
    job = _get_job(job_id)
    canonical = _LOOKUP.get(os.path.basename(filename).lower())
    if canonical not in SUBMISSION_FILES:
        raise _error(
            400, "BAD_FILENAME", "filename must be one of: " + ", ".join(SUBMISSION_FILES)
        )
    path = Path(job["folder"]) / canonical
    if job["status"] != "done" or not path.exists():
        raise _error(
            404,
            "FILE_NOT_READY",
            f"{canonical} is not available: job {job_id} is {job['status']}.",
        )
    return FileResponse(path, media_type="text/csv", filename=canonical)


@app.post("/api/validate")
async def validate_submission(request: Request) -> Dict[str, Any]:
    """Score an existing submission against an instance. 200 even when infeasible."""
    _prune_jobs()
    form = await request.form()
    scenario = _scenario(form.get("scenario"))
    files = await _collect_uploads(request, INSTANCE_FILES + SUBMISSION_FILES)

    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="validate_", dir=str(JOBS_ROOT)))
    try:
        _write_files(folder, files)
        try:
            instance = load_instance(folder)
            return validate(
                instance,
                _read_csv(folder / "SCHEDULE_ACCESS.csv"),
                _read_csv(folder / "SCHEDULE_OCCUPANCY.csv"),
                _read_csv(folder / "RESULTS.csv"),
                scenario,
            )
        except ValueError as exc:
            raise _error(400, "BAD_INSTANCE", f"Could not read the files: {exc}") from exc
    finally:
        shutil.rmtree(folder, ignore_errors=True)
