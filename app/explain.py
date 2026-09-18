"""Plain-English reasons for where each activity landed.

The frontend's "explain panel" shows these next to the timeline. Every sentence
is derived from the instance plus the two schedule tables — nothing here scores
or re-validates anything, and no scoring formula appears in the prose beyond
"late by N days".
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple

from app.validator import _Geometry, _i, _is_eclo, _s, horizon, supply_map

Row = Mapping[str, Any]
Rows = Sequence[Row]

_MAX_SENTENCES = 5


def _pretty(day: dt.date) -> str:
    return day.strftime("%d %b %Y")


def _week_span(week: int, horizon_start: dt.date) -> str:
    start = horizon_start + dt.timedelta(days=7 * (week - 1))
    end = start + dt.timedelta(days=6)
    return f"{_pretty(start)}–{_pretty(end)}"


def _join(items: Sequence[str], limit: int = 3) -> str:
    items = list(items)
    if not items:
        return ""
    shown = items[:limit]
    extra = len(items) - len(shown)
    if len(shown) == 1:
        text = shown[0]
    else:
        text = ", ".join(shown[:-1]) + " and " + shown[-1]
    if extra > 0:
        text += f" (and {extra} more)"
    return text


def explain(
    instance: Mapping[str, Any],
    schedule_access: Rows,
    schedule_occupancy: Rows,
    results: Rows,
) -> Dict[str, List[str]]:
    """Return {activity_id: [2..5 sentences]} describing why it sits where it does."""
    problems: List[Tuple[str, str]] = []
    geo = _Geometry(instance, problems)
    horizon_start, _weeks = horizon(instance)
    supply = supply_map(instance)

    activities = geo.activities
    projects = geo.projects
    results_by_contract = {_s(r.get("contract_number")): r for r in results}

    # access rows per activity, in week order
    access_by_activity: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in schedule_access:
        access_by_activity[_s(row.get("activity_id"))].append(dict(row))
    for rows in access_by_activity.values():
        rows.sort(key=lambda r: _i(r.get("week"), "week", 0))

    # occupancy indexes
    groups_at: Dict[Tuple[str, int], Dict[str, Set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )  # (location, week) -> group -> activities
    occ_by_activity: Dict[str, List[Tuple[int, str, str]]] = defaultdict(list)
    for row in schedule_occupancy:
        activity_id = _s(row.get("activity_id"))
        loc = _s(row.get("location_id"))
        week = _i(row.get("week"), "week", 0)
        group = _s(row.get("co_share_group"))
        groups_at[(loc, week)][group].add(activity_id)
        occ_by_activity[activity_id].append((week, loc, group))

    used_at: Dict[Tuple[str, int], int] = {
        key: len(groups) for key, groups in groups_at.items()
    }

    out: Dict[str, List[str]] = {}
    for activity_id, activity in activities.items():
        rows = access_by_activity.get(activity_id, [])
        contract = _s(activity.get("contract_number"))
        project = projects.get(contract, {})
        sentences: List[str] = []

        # 1. when does it work
        if not rows:
            weeks: List[int] = []
            sentences.append(
                f"{activity_id} has no nights in this schedule — the solver could not "
                f"place any of its {_s(activity.get('total_accesses'))} access-nights."
            )
        else:
            weeks = [_i(r.get("week"), "week", 0) for r in rows]
            spans = [f"week {w} ({_week_span(w, horizon_start)})" for w in weeks]
            sentences.append(
                f"{activity_id} (contract {contract}) works {len(weeks)} "
                f"night{'s' if len(weeks) != 1 else ''}: {_join(spans, 3)}."
            )

        middles: List[str] = []

        # 2. predecessor
        predecessor = _s(activity.get("predecessor_activity_id"))
        if predecessor:
            pred_rows = access_by_activity.get(predecessor, [])
            if pred_rows:
                pred_end = max(_i(r.get("week"), "week", 0) for r in pred_rows)
                middles.append(
                    f"It could not start until {predecessor} was finished, and "
                    f"{predecessor}'s last night is week {pred_end}."
                )
            else:
                middles.append(f"It is held behind its predecessor {predecessor}.")

        # 3. earliest allowed week vs where it actually started, and why it waited
        if weeks:
            try:
                planned_start = dt.date.fromisoformat(
                    _s(activity.get("planned_start_date"))[:10]
                )
                earliest = (planned_start - horizon_start).days // 7 + 1
            except ValueError:
                earliest = None
            if earliest is not None:
                first = min(weeks)
                if first <= earliest:
                    middles.append(
                        f"It started in week {earliest}, the first week allowed by its "
                        f"planned start date of {_pretty(planned_start)}."
                    )
                else:
                    own_locations = sorted(
                        {loc for _w, loc, _g in occ_by_activity.get(activity_id, [])}
                    ) or sorted(geo.route.get(activity_id, set()))
                    full: List[str] = []
                    for skipped in range(earliest, first):
                        for loc in own_locations:
                            cap = supply.get(loc, 0)
                            used = used_at.get((loc, skipped), 0)
                            if cap > 0 and used >= cap:
                                full.append(
                                    f"{loc} in week {skipped} ({used} of {cap} slots taken)"
                                )
                    if full:
                        middles.append(
                            f"It was allowed to start in week {earliest} but waited until "
                            f"week {first}, because the track it needs was already booked "
                            f"out: {_join(sorted(set(full)), 2)}."
                        )
                    else:
                        middles.append(
                            f"It was allowed to start in week {earliest} but waited until "
                            f"week {first} — its own contract's weekly night limit or "
                            f"team limit was the binding constraint, not the track itself."
                        )

        # 4. who it shares possessions with
        sharers: Dict[str, Set[int]] = defaultdict(set)
        for week, loc, group in occ_by_activity.get(activity_id, []):
            for other in groups_at[(loc, week)][group]:
                if other and other != activity_id:
                    sharers[other].add(week)
        if sharers:
            named = [
                f"{other} (week{'s' if len(ws) != 1 else ''} "
                f"{', '.join(str(w) for w in sorted(ws))})"
                for other, ws in sorted(sharers.items())
            ]
            middles.append(
                f"It shares its possession with {_join(named, 3)}, so they are on the "
                f"same night and need no safety buffer between them."
            )
        elif weeks:
            middles.append(
                f"It works alone in its possession; its {_s(project.get('nature_of_activity'))} "
                f"work keeps the neighbouring track clear."
            )

        # 5. ECLO
        eclo_weeks = [
            _i(r.get("week"), "week", 0) for r in rows if _is_eclo(r.get("eclo"))
        ]
        if eclo_weeks:
            middles.append(
                f"{len(eclo_weeks)} of its nights are extended (ECLO) — "
                f"week{'s' if len(eclo_weeks) != 1 else ''} "
                f"{', '.join(str(w) for w in eclo_weeks)} close early or open late, "
                f"which buys half a night of extra work each."
            )

        # 6. did its contract land on time (always last)
        result_row = results_by_contract.get(contract)
        planned_text = _s(project.get("planned_completion_date"))[:10]
        if result_row is not None:
            finish = _s(result_row.get("simulated_completion_date"))[:10]
            overrun = _i(result_row.get("overrun_days"), "overrun_days", 0)
            if overrun > 0:
                tail = (
                    f"Contract {contract} finishes on {finish}, late by {overrun} days "
                    f"against its planned date of {planned_text}."
                )
            else:
                tail = (
                    f"Contract {contract} finishes on {finish}, on time against its "
                    f"planned date of {planned_text}."
                )
        else:
            tail = f"Contract {contract} is due on {planned_text}."

        room = _MAX_SENTENCES - len(sentences) - 1
        sentences.extend(middles[: max(room, 0)])
        sentences.append(tail)
        out[activity_id] = sentences[:_MAX_SENTENCES]

    return out
