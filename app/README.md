# NebulaX PS1 backend (`app/`)

FastAPI service that takes the 8 instance CSVs, runs the OR-Tools scheduler, and
returns a validated schedule plus the 3 submission CSVs.

| File | What it does |
| --- | --- |
| `main.py` | The HTTP API (contract v2, CLAUDE.md §8.2). Jobs, uploads, downloads, validation. |
| `solver.py` | CP-SAT model. `load_instance` / `solve_schedule` / `write_submission`. Owned by Winston. |
| `validator.py` | Our re-implementation of the judges' rule checker. Returns the README §2.7 report. |
| `explain.py` | Plain-English "why is this job on this week" sentences for the explain panel. |

## Run it

**Windows** (Python is the `py` launcher here, `python` is not on PATH):

```powershell
cd C:\Users\Jordan\Documents\ngeebula-clean
.\run.ps1              # port 8000
.\run.ps1 -Port 8020   # any other port
```

or by hand:

```powershell
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Linux / macOS / Render:**

```bash
./run.sh          # port 8000
./run.sh 8020
# or:  python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Environment variables: `JOBS_DIR` (where per-job folders live; default `jobs/`
next to the repo root — it is gitignored and pruned after 2 hours).

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | `{ok, version, jobs_running}` |
| `POST` | `/api/solve` | multipart: the 8 CSVs + `scenario` + optional `time_limit` → `202 {job_id}` |
| `POST` | `/api/solve?wait=true` | same, but blocks and returns the finished job (handy with curl) |
| `GET` | `/api/jobs/{job_id}` | `{status, message, solver_status, elapsed_s, result?}` |
| `GET` | `/api/jobs/{job_id}/download/{SCHEDULE_ACCESS\|SCHEDULE_OCCUPANCY\|RESULTS}.csv` | the generated file, as a download |
| `POST` | `/api/validate` | multipart: 8 instance CSVs + 3 submission CSVs + `scenario` → the report JSON |

`status` is one of `running`, `done`, `infeasible`, `timeout`, `error`.
Errors are always `{"error_code": "...", "message": "..."}` — never a stack trace.
`time_limit` is seconds, default 60, clamped to 5–300.

Files may be sent under any form field name; each file is identified by its own
**file name**, matched case-insensitively against the 8 official names. Anything
else is rejected with `400 BAD_UPLOAD` before a byte is written.

## curl examples

Set `D` to the instance folder and `S` to a submission folder first:

```bash
D="PS1/01_data"
S="PS1/03_submission_sample"
API=http://localhost:8000
```

Health:

```bash
curl $API/api/health
# {"ok":true,"version":"2.0.0","jobs_running":0}
```

Start a solve (async):

```bash
curl -X POST $API/api/solve \
  -F scenario=A -F time_limit=60 \
  -F f1=@$D/01_LINES.csv -F f2=@$D/02_STATIONS.csv \
  -F f3=@$D/03_SECTORS.csv -F f4=@$D/04_LOCATION_SUPPLY.csv \
  -F f5=@$D/05_BUFFER_LOCATION.csv -F f6=@$D/06_PARAMETERS.csv \
  -F f7=@$D/07_PROJECT_DETAILS.csv -F f8=@$D/08_ACTIVITY_DETAILS.csv
# {"job_id":"3f1c..."}
```

Solve and wait (one call, good for scripts):

```bash
curl -X POST "$API/api/solve?wait=true" -F scenario=B ... (same -F file flags)
```

Poll the job:

```bash
curl $API/api/jobs/3f1c...
# {"job_id":"3f1c...","status":"running","message":"Scheduling scenario A…",...}
```

Download a file:

```bash
curl -OJ $API/api/jobs/3f1c.../download/RESULTS.csv
```

Validate an existing submission:

```bash
curl -X POST $API/api/validate -F scenario=A \
  -F f1=@$D/01_LINES.csv ... -F f8=@$D/08_ACTIVITY_DETAILS.csv \
  -F s1=@$S/SCHEDULE_ACCESS.csv -F s2=@$S/SCHEDULE_OCCUPANCY.csv -F s3=@$S/RESULTS.csv
# {"scenario":"A","feasible":false,"hard_violations":[...],"soft_scores":{...},"detail":{...}}
```

## A note on the validator

`validator.py` is a port of `solver-review/check_submission.py` and keeps its
rule semantics exactly, including its strict reading of closures: the
`co_share_group` label is treated as *the night*, so two activities only escape
each other's buffers if they actually share a possession. The organisers' own
sample submission uses several labels per activity-week, so it fails this
reading on **23 closure pairs** while still scoring `priority_weighted_score`
48.3. In other words our checker is stricter than the official one: a clean run
here is sufficient, not necessary.
