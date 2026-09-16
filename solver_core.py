"""Rail maintenance demo. See README.md for input contract and assumptions."""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from ortools.sat.python import cp_model


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timestamps must be ISO strings with a timezone.')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamps must include Z or an offset such as +08:00.')
    if result.second or result.microsecond:
        raise ValueError('Use whole-minute timestamps; seconds must be zero.')
    return result.astimezone(timezone.utc)


def skills(value):
    if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
        raise ValueError('Skills must be a list of nonempty strings.')
    return {x.strip().casefold() for x in value}


def run_solver(jobs, window_start=None, window_end=None, engineers=None,
               blocked_sectors=None, time_limit_seconds=10):
    """Return a JSON-compatible dictionary. No file IO or database writes here.

    Explicit window timestamps are required. Without engineers, returns a
    track-only draft. With engineers, requires explicit skill/headcount/shift
    data, assigns new teams, and prevents engineer double booking.
    """
    warnings = []
    conflicts = []
    def fail(status, message):
        return {'status': status, 'schedule': [], 'ai_explanation': message,
                'conflicts': conflicts, 'warnings': warnings}
    try:
        if not isinstance(jobs, list):
            raise ValueError('jobs must be a list.')
        if not jobs:
            return {'status': 'success', 'schedule': [], 'ai_explanation': 'No jobs supplied.',
                    'conflicts': [], 'warnings': []}
        if window_start is None or window_end is None:
            raise ValueError('Supply window_start and window_end; no operating window is assumed.')
        base, finish = timestamp(window_start), timestamp(window_end)
        horizon = int((finish - base).total_seconds() / 60)
        if not 0 < horizon <= 31 * 24 * 60:
            raise ValueError('Window must be positive and at most 31 days for this demo.')
        if isinstance(time_limit_seconds, bool) or not 0 < time_limit_seconds <= 300:
            raise ValueError('Time limit must be greater than 0 and at most 300 seconds.')
        def minute(value):
            return int((timestamp(value) - base).total_seconds() / 60)
        def iso(value):
            return (base + timedelta(minutes=value)).isoformat()
        def sector(item):
            # Sector is optional: without it the entire line/track is exclusive.
            return tuple(str(item[k]).strip().casefold() for k in ('line', 'track')) + (
                str(item.get('sector', '')).strip().casefold(),)

        records, seen = [], set()
        for job in jobs:
            if not isinstance(job, dict):
                raise ValueError('Each job must be an object.')
            jid = job['id']
            if isinstance(jid, bool) or not isinstance(jid, (int, str)) or str(jid) in seen:
                raise ValueError('Job IDs must be unique integers or strings.')
            seen.add(str(jid))
            for key in ('name', 'line', 'track'):
                if not isinstance(job[key], str) or not job[key].strip():
                    raise ValueError(f'Job {jid}: {key} must be nonempty text.')
            if job.get('status', 'Not started').casefold() != 'not started':
                raise ValueError(f'Job {jid}: only Not started jobs are supported; do not move active/completed work.')
            original = minute(job['scheduled_start'])
            duration = minute(job['scheduled_end']) - original
            if duration <= 0:
                raise ValueError(f'Job {jid}: duration must be positive.')
            latest = min(horizon, minute(job['deadline']))
            earliest = max(0, minute(job['earliest_start'])) if job.get('earliest_start') else 0
            priority = str(job.get('priority', 'Medium')).casefold()
            if priority not in ('urgent', 'high', 'medium', 'low'):
                raise ValueError(f'Job {jid}: priority must be Urgent, High, Medium, or Low.')
            if job.get('assigned_engineers'):
                raise ValueError('Existing engineer assignments must be modelled as commitments; this demo accepts unassigned jobs only.')
            records.append(dict(job=job, id=jid, original=original, duration=duration,
                                latest=latest, earliest=earliest, sector=sector(job),
                                weight={'urgent': 4, 'high': 3, 'medium': 2, 'low': 1}[priority]))
        # Reject inconsistent location granularity instead of missing conflicts.
        sectors = defaultdict(set)
        for r in records:
            sectors[r['sector'][:2]].add(r['sector'][2])
        for block in blocked_sectors or []:
            sectors[sector(block)[:2]].add(sector(block)[2])
        if any('' in values and len(values) > 1 for values in sectors.values()):
            raise ValueError('Use consistent sector fields for all jobs/blocks on a line and track.')
        for i, a in enumerate(records):
            for b in records[i+1:]:
                if a['sector'] == b['sector'] and max(a['original'], b['original']) < min(a['original']+a['duration'], b['original']+b['duration']):
                    conflicts.append({'type': 'original_track_overlap', 'job_ids': [a['id'], b['id']]})
        for r in records:
            if r['duration'] > r['latest'] - r['earliest']:
                return fail('infeasible', f"Job {r['id']} cannot fit its allowed window and deadline.")

        model = cp_model.CpModel()
        track_intervals, engineer_intervals = defaultdict(list), defaultdict(list)
        staff = []
        if engineers is None:
            warnings.append('TRACK-ONLY DRAFT: engineer skills, headcount and availability were not checked.')
        else:
            if isinstance(engineers, dict):
                engineers = engineers['engineers_db']
            if not isinstance(engineers, list):
                raise ValueError('engineers must be a list or an engineers_db object.')
            ids = set()
            for e in engineers:
                eid = e.get('id', e.get('work_email'))
                if eid is None or str(eid) in ids:
                    raise ValueError('Engineers need a unique id or work_email.')
                ids.add(str(eid))
                if 'available_start' not in e or 'available_end' not in e:
                    raise ValueError('Each engineer needs available_start and available_end; Available/Busy labels are insufficient.')
                lo, hi = minute(e['available_start']), minute(e['available_end'])
                if hi <= lo:
                    raise ValueError('Engineer availability end must follow start.')
                if e.get('projects assigned'):
                    raise ValueError('Resolve existing projects assigned into free availability before using engineer mode.')
                staff.append((eid, skills(e['skillset']), lo, hi))

        objective = []
        for r in records:
            label = str(r['id'])
            start = model.new_int_var(r['earliest'], r['latest'] - r['duration'], 'start_'+label)
            end = model.new_int_var(r['earliest'] + r['duration'], r['latest'], 'end_'+label)
            interval = model.new_interval_var(start, r['duration'], end, 'job_'+label)
            track_intervals[r['sector']].append(interval)
            r.update(start=start, end=end, assignments=[])
            bound = max(abs(r['earliest']-r['original']), abs(r['latest']-r['duration']-r['original']))
            change = model.new_int_var(0, bound, 'change_'+label)
            model.add_abs_equality(change, start-r['original'])
            objective.append(r['weight']*change)
            if engineers is not None:
                required = skills(r['job']['required_skills'])
                count = r['job']['engineers_required']
                if not required or type(count) is not int or count < 1:
                    raise ValueError('Jobs need nonempty required_skills and positive integer engineers_required.')
                for index, (eid, known, lo, hi) in enumerate(staff):
                    if required <= known and min(hi, r['latest']) - max(lo, r['earliest']) >= r['duration']:
                        chosen = model.new_bool_var(f'assign_{label}_{index}')
                        model.add(start >= lo).only_enforce_if(chosen)
                        model.add(end <= hi).only_enforce_if(chosen)
                        optional = model.new_optional_interval_var(start, r['duration'], end, chosen, f'work_{label}_{index}')
                        engineer_intervals[str(eid)].append(optional)
                        r['assignments'].append((eid, chosen))
                if len(r['assignments']) < count:
                    return fail('infeasible', f"Job {r['id']} has too few fully qualified engineers with sufficient availability.")
                model.add(sum(x for _, x in r['assignments']) == count)
        closures = defaultdict(list)
        for block in blocked_sectors or []:
            lo, hi = minute(block['start']), minute(block['end'])
            if hi <= lo:
                raise ValueError('Sector closure end must follow start.')
            lo, hi = max(0, lo), min(horizon, hi)
            if hi > lo:
                closures[sector(block)].append((lo, hi))
        for key, windows in closures.items():
            merged = []
            for lo, hi in sorted(windows):
                if merged and lo <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
                else:
                    merged.append((lo, hi))
            for index, (lo, hi) in enumerate(merged):
                track_intervals[key].append(model.new_fixed_size_interval_var(lo, hi-lo, f'closure_{key}_{index}'))
        for intervals in list(track_intervals.values()) + list(engineer_intervals.values()):
            model.add_no_overlap(intervals)
        # Priority protects original times more strongly; it does NOT mean high first.
        model.minimize(sum(objective))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit_seconds)
        status = solver.solve(model)
        if status == cp_model.INFEASIBLE:
            return fail('infeasible', 'All jobs cannot fit together under the supplied constraints. Extend availability, add qualified staff, or explicitly defer jobs; none were silently dropped.')
        if status == cp_model.MODEL_INVALID:
            return fail('error', 'Invalid optimisation model: '+model.validate())
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return fail('unknown', 'Search ended without a schedule; this does not prove impossibility.')
        schedule = []
        for r in records:
            job = r['job']
            start, end = solver.value(r['start']), solver.value(r['end'])
            output = {k: job[k] for k in ('name', 'line', 'track')}
            output.update(job_id=r['id'], priority=job.get('priority', 'Medium'), status=job.get('status', 'Not started'),
                          scheduled_start=iso(start), scheduled_end=iso(end),
                          original_start=job['scheduled_start'], shift_minutes=start-r['original'],
                          assigned_engineers=([eid for eid, chosen in r['assignments'] if solver.value(chosen)] if engineers is not None else None))
            if 'sector' in job:
                output['sector'] = job['sector']
            schedule.append(output)
        schedule.sort(key=lambda x: (x['scheduled_start'], str(x['job_id'])))
        moved = sum(x['shift_minutes'] != 0 for x in schedule)
        return {'status': 'success', 'solver_status': solver.status_name(status), 'schedule': schedule,
                'engineers_checked': engineers is not None, 'conflicts': conflicts, 'warnings': warnings,
                'objective_value': solver.objective_value,
                'ai_explanation': f'Scheduled {len(schedule)} jobs; moved {moved}. Same-location overlaps are prevented and deadlines respected. Objective: minimise priority-weighted changes from original start times. ' + ('Engineer assignments checked.' if engineers is not None else 'Engineer feasibility NOT checked.')}
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return fail('error', f'Invalid input: {exc}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', default=str(Path(__file__).with_name('jobs.json')))
    parser.add_argument('--config', default=str(Path(__file__).with_name('config.json')))
    parser.add_argument('--engineers', help='Optional engineer JSON with explicit shift times')
    args = parser.parse_args()
    try:
        with open(args.jobs, encoding='utf-8') as f:
            jobs = json.load(f)
        with open(args.config, encoding='utf-8') as f:
            config = json.load(f)
        engineers = None
        if args.engineers:
            with open(args.engineers, encoding='utf-8') as f:
                engineers = json.load(f)
        result = run_solver(jobs, engineers=engineers, **config)
    except (OSError, ValueError, TypeError) as exc:
        result = {'status': 'error', 'schedule': [], 'ai_explanation': str(exc)}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
