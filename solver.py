"""Adapter between SQL-backed FastAPI inputs and the CP-SAT engine."""
import datetime as dt
import json
try:
    from .solver_core import run_solver
except ImportError:
    from solver_core import run_solver

UTC = dt.timezone.utc
SGT = dt.timezone(dt.timedelta(hours=8))

def as_utc(value):
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, dt.datetime):
        raise ValueError('Expected a datetime.')
    # Contract: naive SQLite timestamps are stored UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

def next_window():
    # Always the next complete 00:30-to-05:00 SGT window; no past work.
    now = dt.datetime.now(SGT)
    start = now.replace(hour=0, minute=30, second=0, microsecond=0)
    if start < now:
        start += dt.timedelta(days=1)
    return start, start + dt.timedelta(hours=4, minutes=30)

def solve_mrt_schedule(jobs, engineers, window_start=None, window_end=None):
    """Returns the full result dictionary, including explicit diagnostics.

    is_available means available throughout the selected window for this MVP.
    Qualifications require exact skill matches (ignoring case/whitespace).
    """
    if (window_start is None) != (window_end is None):
        return {'status':'error','schedule':[], 'ai_explanation':'Provide both window endpoints.'}
    if window_start is None:
        window_start, window_end = next_window()
    try:
        start, end = as_utc(window_start), as_utc(window_end)
        mapped = []
        for j in jobs:
            duration = j['duration_mins']
            if type(duration) is not int or duration <= 0:
                raise ValueError(f"Job {j['id']}: duration_mins must be a positive integer.")
            required = j.get('required_skills')
            if isinstance(required, str):
                required = json.loads(required)
            if not required:
                raise ValueError(f"Job {j['id']}: required_skills is missing; review the job requirements.")
            if j.get('status', 'Not started') != 'Not started' or j.get('is_approved'):
                raise ValueError('This version only replans unapproved Not started jobs. Active/approved work must not be moved.')
            original = as_utc(j['scheduled_start']) if j.get('scheduled_start') else start
            mapped.append(dict(id=j['id'], name=j['name'], line=j['line'], track=j['track'],
                deadline=as_utc(j['deadline']).isoformat(), priority=j['priority'], status='Not started',
                scheduled_start=original.isoformat(), scheduled_end=(original+dt.timedelta(minutes=duration)).isoformat(),
                required_skills=required, engineers_required=j['engineers_needed']))
        staff = [dict(id=e['id'], skillset=e['skills'], available_start=start.isoformat(), available_end=end.isoformat())
                 for e in engineers if e['is_available']]
        result = run_solver(mapped, start.isoformat(), end.isoformat(), engineers=staff, time_limit_seconds=10)
        result['window_start'] = start.isoformat()
        result['window_end'] = end.isoformat()
        result.setdefault('warnings', []).append('MVP assumption: is_available means free for this entire window. Travel, breaks, line authorisations and sector closures are not supplied by this backend.')
        for row in result['schedule']:
            row['id'] = row['job_id']
            row['scheduled_start_min'] = int((as_utc(row['scheduled_start'])-start).total_seconds()/60)
            row['scheduled_end_min'] = int((as_utc(row['scheduled_end'])-start).total_seconds()/60)
        return result
    except (ValueError, TypeError, KeyError) as exc:
        return {'status':'error','schedule':[], 'ai_explanation':str(exc)}
