from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

try:
    from ortools.sat.python import cp_model
except ImportError as exc:  # pragma: no cover - gives a clearer error on a new machine
    raise ImportError(
        "OR-Tools is required. Install it with: pip install ortools"
    ) from exc


TABLE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "lines": ("lines", "01_LINES.csv", "01_LINES", "LINES"),
    "stations": ("stations", "02_STATIONS.csv", "02_STATIONS", "STATIONS"),
    "sectors": ("sectors", "03_SECTORS.csv", "03_SECTORS", "SECTORS"),
    "location_supply": (
        "location_supply",
        "04_LOCATION_SUPPLY.csv",
        "04_LOCATION_SUPPLY",
        "LOCATION_SUPPLY",
    ),
    "buffer_location": (
        "buffer_location",
        "05_BUFFER_LOCATION.csv",
        "05_BUFFER_LOCATION",
        "BUFFER_LOCATION",
    ),
    "parameters": (
        "parameters",
        "06_PARAMETERS.csv",
        "06_PARAMETERS",
        "PARAMETERS",
    ),
    "project_details": (
        "project_details",
        "07_PROJECT_DETAILS.csv",
        "07_PROJECT_DETAILS",
        "PROJECT_DETAILS",
    ),
    "activity_details": (
        "activity_details",
        "08_ACTIVITY_DETAILS.csv",
        "08_ACTIVITY_DETAILS",
        "ACTIVITY_DETAILS",
    ),
}

REQUIRED_TABLES = (
    "sectors",
    "location_supply",
    "buffer_location",
    "parameters",
    "project_details",
    "activity_details",
)

PRIORITY_BASE_WEIGHT = {1: 100, 2: 10, 3: 1}
ACTIVITY_PRIORITY_TENTHS = {1: 3, 2: 2, 3: 0}


PHYSICAL_NIGHTS_PER_WEEK = 7

# S6: deterministic by default. See the note where the parameter is applied.
DEFAULT_NUM_WORKERS = 1

# S5: if the instance cannot be scheduled inside the official horizon we retry with a
# longer one rather than telling the judges "impossible" (README 1, "Keep Scheduling
# Under Congestion"). These are multipliers of `horizon_weeks`, tried in order. 1.5 and
# 2.0 handle mild congestion; the larger ones exist because a horizon that is simply
# far too short (say 12 weeks for work that cannot physically finish before week 30)
# is not fixed by doubling it.
HORIZON_EXTENSION_FACTORS = (1.5, 2.0, 3.0, 4.0)



def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any, field: str) -> int:
    text = _clean(value)
    if text == "":
        raise ValueError(f"Missing integer value for {field}")
    try:
        return int(float(text))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer for {field}: {value!r}") from exc


def _parse_date(value: Any, field: str) -> dt.date:
    text = _clean(value)
    if not text:
        raise ValueError(f"Missing date value for {field}")
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date for {field}: {value!r}") from exc


def _records(value: Any) -> List[Dict[str, Any]]:
    """Accept list[dict], tuple[dict], pandas DataFrame, or similar records."""
    if value is None:
        return []
    if isinstance(value, list):
        return [dict(row) for row in value]
    if isinstance(value, tuple):
        return [dict(row) for row in value]
    if hasattr(value, "to_dict"):
        try:
            rows = value.to_dict("records")
            return [dict(row) for row in rows]
        except TypeError:
            pass
    if isinstance(value, Mapping):
        # A single row is accepted for convenience.
        return [dict(value)]
    raise TypeError(f"Unsupported table type: {type(value).__name__}")


def _find_table(data: Mapping[str, Any], canonical: str) -> List[Dict[str, Any]]:
    aliases = TABLE_ALIASES[canonical]
    for alias in aliases:
        if alias in data:
            return _records(data[alias])
    lower_lookup = {str(k).lower(): k for k in data}
    for alias in aliases:
        key = lower_lookup.get(alias.lower())
        if key is not None:
            return _records(data[key])
    return []


def _normalise_instance(data: Mapping[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    tables = {name: _find_table(data, name) for name in TABLE_ALIASES}
    missing = [name for name in REQUIRED_TABLES if not tables[name]]
    if missing:
        raise ValueError(
            "Missing required PS1 tables: " + ", ".join(missing)
        )
    return tables


def _parameters_dict(rows: Sequence[Mapping[str, Any]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for row in rows:
        key = _clean(row.get("key"))
        if key:
            result[key] = _clean(row.get("value"))
    return result


def _week_of(date_value: dt.date, horizon_start: dt.date) -> int:
    """Week 1 is horizon_start .. horizon_start+6 days."""
    return ((date_value - horizon_start).days // 7) + 1


def _week_end_date(week: int, horizon_start: dt.date) -> dt.date:
    return horizon_start + dt.timedelta(days=week * 7 - 1)


def _date_day_index(date_value: dt.date, horizon_start: dt.date) -> int:
    return (date_value - horizon_start).days

def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_instance(folder: str | Path) -> Dict[str, List[Dict[str, str]]]:
    """
    Load the official eight CSV files from a folder.

    Returns canonical keys such as `project_details` and `activity_details`.
    """
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(folder)

    result: Dict[str, List[Dict[str, str]]] = {}
    for canonical, aliases in TABLE_ALIASES.items():
        csv_name = next((name for name in aliases if name.endswith(".csv")), None)
        if not csv_name:
            continue
        path = folder / csv_name
        if path.exists():
            result[canonical] = _read_csv(path)

    missing = [name for name in REQUIRED_TABLES if name not in result]
    if missing:
        raise ValueError(
            f"{folder} is missing required files for: {', '.join(missing)}"
        )
    return result


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_submission(result: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
    """Write the three official submission CSVs for one scenario."""
    if result.get("status") != "success":
        raise ValueError("Cannot write submission because the solver did not succeed")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    access_path = output_dir / "SCHEDULE_ACCESS.csv"
    occupancy_path = output_dir / "SCHEDULE_OCCUPANCY.csv"
    results_path = output_dir / "RESULTS.csv"

    _write_csv(
        access_path,
        ["activity_id", "access_seq", "week", "eclo", "access_night"],
        result["schedule_access"],
    )
    _write_csv(
        occupancy_path,
        ["activity_id", "week", "location_id", "co_share_group"],
        result["schedule_occupancy"],
    )
    _write_csv(
        results_path,
        ["scenario", "contract_number", "simulated_completion_date", "overrun_days"],
        result["results"],
    )

    return {
        "SCHEDULE_ACCESS.csv": str(access_path),
        "SCHEDULE_OCCUPANCY.csv": str(occupancy_path),
        "RESULTS.csv": str(results_path),
    }


def _parse_track_location(location_id: str) -> Tuple[str, str, str, str]:
    """
    Parse e.g. SEC:ALP:S03_S04:EB or PLAT:ALP:S03:EB.
    Returns (kind, line, middle, bound).
    """
    parts = _clean(location_id).split(":")
    if len(parts) != 4:
        raise ValueError(f"Unexpected location_id format: {location_id!r}")
    kind, line, middle, bound = parts
    if kind not in {"SEC", "PLAT"}:
        raise ValueError(f"Unknown location kind in {location_id!r}")
    if bound not in {"EB", "WB"}:
        raise ValueError(f"Unknown bound in {location_id!r}")
    return kind, line, middle, bound


def _sector_base_id(location_id: str) -> str:
    kind, line, middle, _bound = _parse_track_location(location_id)
    if kind != "SEC":
        raise ValueError(f"Activity start/end must be sector locations: {location_id}")
    return f"SEC:{line}:{middle}"


def _swap_bound(location_id: str) -> str:
    kind, line, middle, bound = _parse_track_location(location_id)
    return f"{kind}:{line}:{middle}:{'WB' if bound == 'EB' else 'EB'}"


def _line_of_location(location_id: str) -> str:
    return _parse_track_location(location_id)[1]


def _build_sector_index(
    sectors: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    by_line: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for raw in sectors:
        row = dict(raw)
        sector_id = _clean(row.get("sector_id"))
        line = _clean(row.get("line_code"))
        if not sector_id or not line:
            raise ValueError("SECTORS row missing sector_id or line_code")
        row["seq"] = _as_int(row.get("seq"), "SECTORS.seq")
        by_id[sector_id] = row
        by_line[line].append(row)

    for line in by_line:
        by_line[line].sort(key=lambda r: int(r["seq"]))

    return by_id, dict(by_line)


def _normalise_nature(value: Any) -> str:
    """
    S3: `nature_of_works` / `nature_of_activity` are free text typed by two different
    people into two different files. Compare them lower-cased, trimmed, with runs of
    whitespace collapsed, so `Non-live  (Consist) ` matches `non-live (consist)`.
    """
    return " ".join(_clean(value).lower().split())


def _is_live_nature(normalised_nature: str) -> bool:
    """
    True for `Live`, `Live rail`, `Live (750V)`; False for `Non-live (Consist)`.
    A plain substring test would wrongly match `non-live`, hence the prefix test.
    """
    return (
        normalised_nature == "live"
        or normalised_nature.startswith("live ")
        or normalised_nature.startswith("live(")
    )


def _truthy(value: Any) -> bool:
    """`1`, `true`, `yes`, `y`, `t` (any case, any surrounding space) mean yes."""
    return _clean(value).lower() in {"1", "true", "yes", "y", "t"}


def _build_interchange_index(
    stations: Sequence[Mapping[str, Any]],
    sectors: Sequence[Mapping[str, Any]],
) -> Tuple[Set[str], Set[str]]:
    """
    S2: work out which stations are interchanges and which tunnel sectors are the
    shared cross-line ones, from the data instead of hard-coding `H01`/`H02`/`H01_H02`.

    Returns (interchange_station_ids, shared_sector_base_ids) where a base id looks
    like `SEC:ALP:H01_H02` (no bound).
    """
    stations_by_line: Dict[str, Set[str]] = defaultdict(set)
    interchange: Set[str] = set()
    for row in stations:
        station_id = _clean(row.get("station_id"))
        if not station_id:
            continue
        stations_by_line[_clean(row.get("line_code"))].add(station_id)
        if _truthy(row.get("is_interchange")):
            interchange.add(station_id)

    if not stations_by_line:
        # 02_STATIONS is optional in this loader; rebuild the line -> stations map from
        # the sector endpoints so the fallback below still has something to work with.
        for row in sectors:
            line = _clean(row.get("line_code"))
            for key in ("from_station_id", "to_station_id"):
                station_id = _clean(row.get(key))
                if station_id:
                    stations_by_line[line].add(station_id)

    if not interchange:
        # Fallback when 02_STATIONS has no usable `is_interchange` column: a station
        # that appears on more than one line is by definition an interchange.
        seen: Dict[str, int] = defaultdict(int)
        for line_stations in stations_by_line.values():
            for station_id in line_stations:
                seen[station_id] += 1
        interchange = {s for s, n in seen.items() if n > 1}

    shared: Set[str] = set()
    for row in sectors:
        sector_id = _clean(row.get("sector_id"))
        if sector_id and _truthy(row.get("is_shared")):
            shared.add(sector_id)

    if not shared:
        # Fallback (this is what the public instance needs -- it ships `is_shared=0`
        # on every row, including the interchange tunnel): a sector running between
        # two interchange stations is the cross-line tunnel.
        for row in sectors:
            sector_id = _clean(row.get("sector_id"))
            if not sector_id:
                continue
            if (
                _clean(row.get("from_station_id")) in interchange
                and _clean(row.get("to_station_id")) in interchange
            ):
                shared.add(sector_id)

    return interchange, shared


def _locations_for_sector_rows(
    sector_rows: Sequence[Mapping[str, Any]],
    line: str,
    bound: str,
) -> Set[str]:
    locations: Set[str] = set()
    stations: Set[str] = set()

    for row in sector_rows:
        sector_id = _clean(row["sector_id"])
        # sector_id already begins SEC:<line>:...
        locations.add(f"{sector_id}:{bound}")
        stations.add(_clean(row["from_station_id"]))
        stations.add(_clean(row["to_station_id"]))

    for station in stations:
        locations.add(f"PLAT:{line}:{station}:{bound}")

    return locations


def _activity_route_and_closure(
    activity: Mapping[str, Any],
    project: Mapping[str, Any],
    sector_by_id: Mapping[str, Mapping[str, Any]],
    sectors_by_line: Mapping[str, Sequence[Mapping[str, Any]]],
    buffer_by_nature: Mapping[str, int],
    mirror_by_nature: Mapping[str, bool],
    all_location_ids: Set[str],
    interchange_stations: Set[str],
    shared_sector_bases: Set[str],
    missing_locations: Set[str],
) -> Tuple[Set[str], Set[str], Set[str]]:

    start_location = _clean(activity.get("start_location_id"))
    end_location = _clean(activity.get("end_location_id"))

    _skind, start_line, _smid, start_bound = _parse_track_location(start_location)
    _ekind, end_line, _emid, end_bound = _parse_track_location(end_location)
    if start_line != end_line or start_bound != end_bound:
        raise ValueError(
            f"Activity {activity.get('activity_id')} crosses line/bound in start/end; "
            "the public format expects one line and one bound per activity"
        )

    start_base = _sector_base_id(start_location)
    end_base = _sector_base_id(end_location)
    if start_base not in sector_by_id or end_base not in sector_by_id:
        raise ValueError(
            f"Activity {activity.get('activity_id')} references a sector missing from SECTORS"
        )

    start_seq = int(sector_by_id[start_base]["seq"])
    end_seq = int(sector_by_id[end_base]["seq"])
    low_seq, high_seq = sorted((start_seq, end_seq))

    line_rows = list(sectors_by_line[start_line])
    route_rows = [r for r in line_rows if low_seq <= int(r["seq"]) <= high_seq]
    route = _locations_for_sector_rows(route_rows, start_line, start_bound)

    # S3: an unknown nature_of_works must not silently mean "no buffer".
    nature_raw = _clean(project.get("nature_of_activity"))
    nature = _normalise_nature(nature_raw)
    if nature not in buffer_by_nature:
        known = ", ".join(sorted(buffer_by_nature)) or "(none)"
        raise ValueError(
            f"Contract {project.get('contract_number')} has nature_of_activity "
            f"{nature_raw!r}, which has no matching row in 05_BUFFER_LOCATION "
            f"(nature_of_works). Known natures: {known}. "
            "Fix the data so the two tables agree; refusing to guess a buffer size."
        )
    buffer_size = buffer_by_nature[nature]
    closure_rows = [
        r
        for r in line_rows
        if low_seq - buffer_size <= int(r["seq"]) <= high_seq + buffer_size
    ]
    closure = _locations_for_sector_rows(closure_rows, start_line, start_bound)

    if mirror_by_nature.get(nature, False):
        # Live work cuts traction power, so the closure mirrors onto the other bound.
        closure |= {_swap_bound(loc) for loc in list(closure)}

    if _is_live_nature(nature):
        # S2: the cross-line interchange crossover, derived from the data rather than
        # from the literal names H01 / H02 / H01_H02 (README 2.2, 2.4 rule 3).
        reaches_interchange = False
        for loc in closure:
            kind, line, middle, _bound = _parse_track_location(loc)
            if kind == "PLAT" and middle in interchange_stations:
                reaches_interchange = True
                break
            if kind == "SEC" and f"SEC:{line}:{middle}" in shared_sector_bases:
                reaches_interchange = True
                break

        if reaches_interchange:
            other_lines = [line for line in sectors_by_line if line != start_line]
            for other in other_lines:
                other_shared = [
                    _clean(r["sector_id"])
                    for r in sectors_by_line[other]
                    if _clean(r["sector_id"]) in shared_sector_bases
                ]
                other_interchange = sorted(
                    {
                        station
                        for r in sectors_by_line[other]
                        for station in (
                            _clean(r.get("from_station_id")),
                            _clean(r.get("to_station_id")),
                        )
                        if station in interchange_stations
                    }
                )
                for bound in ("EB", "WB"):
                    for sector_id in other_shared:
                        closure.add(f"{sector_id}:{bound}")
                    for station in other_interchange:
                        closure.add(f"PLAT:{other}:{station}:{bound}")

    # S7: route locations with no row in 04_LOCATION_SUPPLY are reported, not dropped
    # in silence. (Closure ids are built defensively and may legitimately not exist.)
    missing_locations |= route - all_location_ids

    # Ignore defensive closure IDs that are not actual capacity locations.
    closure &= all_location_ids
    route &= all_location_ids
    affected_lines = {_line_of_location(loc) for loc in closure}

    if not route:
        raise ValueError(
            f"Activity {activity.get('activity_id')} expands to no valid occupancy locations"
        )

    return route, closure, affected_lines


def _co_share_pair_allowed(
    access_type_a: str,
    access_type_b: str,
    route_a: Set[str],
    route_b: Set[str],
    closure_a: Set[str],
    closure_b: Set[str],
) -> bool:

    pair = {access_type_a, access_type_b}
    compatible_types = (
        access_type_a == "C" and access_type_b == "C"
    ) or pair == {"PC", "C"}
    if not compatible_types:
        return False

    # README 2.4 rule 5 (Co-Sharing Exemption): two activities that sit in the same
    # (location_id, week, co_share_group) form ONE possession. Members of a possession
    # are "exempt from each other's closures" -- that exemption covers the buffer zones
    # too, because there are simply "no buffers between them". So the only thing we need
    # is a real worksite (route) location in common, which is what makes them share a
    # possession in the first place.
    #
    # The previous test also demanded that the two BUFFER zones coincide
    # (`collision <= shared_real_worksite`). That is a stricter rule than the README
    # states: two co-workers standing on the same sector always have differently-shaped
    # buffer fans, so the test failed for almost every legal C/C and PC/C pair, forced
    # them onto separate nights, and made Scenario A INFEASIBLE on the public data
    # (the organisers' own sample proves A is feasible).
    return bool(route_a & route_b)



def _validate_predecessors(activities: Mapping[str, Mapping[str, Any]]) -> None:
    """Catch unknown predecessor IDs and cycles before CP-SAT is built."""
    graph: Dict[str, Optional[str]] = {}
    for activity_id, row in activities.items():
        predecessor = _clean(row.get("predecessor_activity_id")) or None
        if predecessor and predecessor not in activities:
            raise ValueError(
                f"Activity {activity_id} references unknown predecessor {predecessor}"
            )
        if predecessor == activity_id:
            raise ValueError(f"Activity {activity_id} cannot depend on itself")
        graph[activity_id] = predecessor

    WHITE, GREY, BLACK = 0, 1, 2
    state = {activity_id: WHITE for activity_id in activities}

    def visit(node: str, stack: List[str]) -> None:
        if state[node] == BLACK:
            return
        if state[node] == GREY:
            cycle_start = stack.index(node) if node in stack else 0
            cycle = stack[cycle_start:] + [node]
            raise ValueError("Predecessor cycle detected: " + " -> ".join(cycle))

        state[node] = GREY
        stack.append(node)
        predecessor = graph[node]
        if predecessor:
            visit(predecessor, stack)
        stack.pop()
        state[node] = BLACK

    for activity_id in activities:
        if state[activity_id] == WHITE:
            visit(activity_id, [])


def solve_schedule(
    data: Mapping[str, Any],
    scenario: str = "A",
    *,
    time_limit_seconds: float = 30.0,
    num_workers: Optional[int] = None,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """
    Solve one scenario and return the three submission tables plus diagnostics.

    S5 (graceful degradation): README 1 says the solver "must not stop or declare the
    case impossible". If the official horizon is too short for the work on offer, we do
    not hand back an empty answer -- we retry with a longer horizon (x1.5, then x2) and
    flag that the plan runs past the official end date. Only if even that fails do we
    return `status: "failure"`, and then with the solver's own status and a message
    that says whether it was INFEASIBLE or merely out of time.
    """
    result = _solve_once(
        data,
        scenario,
        time_limit_seconds=time_limit_seconds,
        num_workers=num_workers,
        random_seed=random_seed,
    )
    if result["status"] == "success":
        return result

    base_weeks = int(result["metrics"]["horizon_weeks"])
    last_failure = result

    # `minimum_horizon_weeks` is the arithmetic floor: no activity can finish before
    # (its planned start week + one night per week). A horizon shorter than that is
    # infeasible no matter how the nights are arranged, so it is always worth trying.
    candidates = {int(math.ceil(base_weeks * f)) for f in HORIZON_EXTENSION_FACTORS}
    floor_weeks = int(result["metrics"].get("minimum_horizon_weeks") or 0)
    if floor_weeks:
        candidates.add(floor_weeks)
        candidates.add(2 * floor_weeks)

    for extended in sorted(w for w in candidates if w > base_weeks):
        print(
            f"Scenario {result['scenario']}: {result['solver_status']} over "
            f"{base_weeks} weeks; retrying with a {extended}-week horizon."
        )
        retry = _solve_once(
            data,
            scenario,
            time_limit_seconds=time_limit_seconds,
            num_workers=num_workers,
            random_seed=random_seed,
            horizon_weeks_override=extended,
        )
        if retry["status"] == "success":
            retry["horizon_extended_to"] = extended
            retry.setdefault("warnings", []).append(
                f"The instance could not be scheduled inside its official "
                f"{base_weeks}-week horizon, so the horizon was extended to "
                f"{extended} weeks. Some work therefore runs past the official end of "
                "the programme and the overrun figures in RESULTS.csv reflect that."
            )
            return retry
        last_failure = retry

    last_failure["horizon_extended_to"] = None
    return last_failure


def _solve_once(
    data: Mapping[str, Any],
    scenario: str,
    *,
    time_limit_seconds: float,
    num_workers: Optional[int],
    random_seed: int,
    horizon_weeks_override: Optional[int] = None,
) -> Dict[str, Any]:
    """Build and solve the CP-SAT model for one horizon length. See solve_schedule."""

    scenario = _clean(scenario).upper()
    if scenario not in {"A", "B", "C"}:
        raise ValueError("scenario must be one of: A, B, C")

    warnings: List[str] = []

    tables = _normalise_instance(data)
    params = _parameters_dict(tables["parameters"])
    horizon_start = _parse_date(params.get("horizon_start"), "horizon_start")
    official_horizon_weeks = _as_int(params.get("horizon_weeks"), "horizon_weeks")
    horizon_weeks = (
        official_horizon_weeks
        if horizon_weeks_override is None
        else int(horizon_weeks_override)
    )
    weeks = list(range(1, horizon_weeks + 1))
    physical_nights = list(range(1, PHYSICAL_NIGHTS_PER_WEEK + 1))

    projects: Dict[str, Dict[str, Any]] = {}
    for row in tables["project_details"]:
        contract = _clean(row.get("contract_number"))
        if not contract:
            raise ValueError("PROJECT_DETAILS row missing contract_number")
        projects[contract] = dict(row)

    activities: Dict[str, Dict[str, Any]] = {}
    for row in tables["activity_details"]:
        activity_id = _clean(row.get("activity_id"))
        if not activity_id:
            raise ValueError("ACTIVITY_DETAILS row missing activity_id")
        contract = _clean(row.get("contract_number"))
        if contract not in projects:
            raise ValueError(
                f"Activity {activity_id} references unknown contract {contract!r}"
            )
        activities[activity_id] = dict(row)

    _validate_predecessors(activities)

    sector_by_id, sectors_by_line = _build_sector_index(tables["sectors"])

    supply: Dict[str, int] = {}
    for row in tables["location_supply"]:
        location_id = _clean(row.get("location_id"))
        supply[location_id] = _as_int(row.get("supply_capacity"), "supply_capacity")
    all_location_ids = set(supply)

    # S3: keys are normalised so the buffer table and PROJECT_DETAILS always line up.
    buffer_by_nature: Dict[str, int] = {}
    mirror_by_nature: Dict[str, bool] = {}
    for row in tables["buffer_location"]:
        nature = _normalise_nature(row.get("nature_of_works"))
        if not nature:
            continue
        buffer_by_nature[nature] = _as_int(
            row.get("up_to_buffer_sectors"), "up_to_buffer_sectors"
        )
        # `opposite_bound_required` is the data's own name for the Live mirroring rule.
        # If the column is missing we fall back to "Live means mirror" (README 2.3).
        if "opposite_bound_required" in row:
            mirror_by_nature[nature] = _truthy(row.get("opposite_bound_required"))
        else:
            mirror_by_nature[nature] = _is_live_nature(nature)

    interchange_stations, shared_sector_bases = _build_interchange_index(
        tables["stations"], tables["sectors"]
    )

    activity_ids = list(activities)
    missing_locations: Set[str] = set()

    # Pre-compute route, closure, line effects and date limits.
    route: Dict[str, Set[str]] = {}
    closure: Dict[str, Set[str]] = {}
    affected_lines: Dict[str, Set[str]] = {}
    earliest_week: Dict[str, int] = {}
    activity_contract: Dict[str, str] = {}
    activity_access_type: Dict[str, str] = {}
    activity_nature: Dict[str, str] = {}

    for activity_id, activity in activities.items():
        contract = _clean(activity.get("contract_number"))
        project = projects[contract]
        activity_contract[activity_id] = contract
        activity_access_type[activity_id] = _clean(project.get("access_type"))
        activity_nature[activity_id] = _normalise_nature(
            project.get("nature_of_activity")
        )

        start_date = _parse_date(
            activity.get("planned_start_date"),
            f"{activity_id}.planned_start_date",
        )
        earliest_week[activity_id] = max(1, _week_of(start_date, horizon_start))

        r, c, lines = _activity_route_and_closure(
            activity,
            project,
            sector_by_id,
            sectors_by_line,
            buffer_by_nature,
            mirror_by_nature,
            all_location_ids,
            interchange_stations,
            shared_sector_bases,
            missing_locations,
        )
        route[activity_id] = r
        closure[activity_id] = c
        affected_lines[activity_id] = lines

    # S7: never drop route locations in silence.
    if missing_locations:
        message = (
            f"{len(missing_locations)} route location(s) have no row in "
            "04_LOCATION_SUPPLY and were left out of the occupancy output: "
            + ", ".join(sorted(missing_locations))
        )
        warnings.append(message)
        print(f"WARNING: {message}")

    # Arithmetic floor on the horizon: an activity can take at most one access-night a
    # week, so it cannot finish before (planned start week + nights needed - 1). Used by
    # solve_schedule to pick sensible retry horizons (S5).
    minimum_horizon_weeks = 1
    for activity_id, activity in activities.items():
        nights_needed = _as_int(
            activity.get("total_accesses"), f"{activity_id}.total_accesses"
        )
        minimum_horizon_weeks = max(
            minimum_horizon_weeks,
            earliest_week[activity_id] + max(0, nights_needed - 1),
        )

    # Activity lists per actual occupied location speed up location constraints.
    activities_at_location: Dict[str, List[str]] = defaultdict(list)
    for activity_id in activity_ids:
        for location_id in route[activity_id]:
            activities_at_location[location_id].append(activity_id)

    model = cp_model.CpModel()

    scheduled: Dict[Tuple[str, int], cp_model.IntVar] = {}
    normal: Dict[Tuple[str, int], cp_model.IntVar] = {}
    eclo: Dict[Tuple[str, int], cp_model.IntVar] = {}
    physical: Dict[Tuple[str, int, int], cp_model.IntVar] = {}

    for activity_id in activity_ids:
        for week in weeks:
            s = model.NewBoolVar(f"scheduled__{activity_id}__w{week}")
            n = model.NewBoolVar(f"normal__{activity_id}__w{week}")
            e = model.NewBoolVar(f"eclo__{activity_id}__w{week}")
            scheduled[activity_id, week] = s
            normal[activity_id, week] = n
            eclo[activity_id, week] = e

            model.Add(n + e == s)

            # Planned start date: impossible before the planned start week.
            if week < earliest_week[activity_id]:
                model.Add(s == 0)

            if scenario == "A":
                model.Add(e == 0)

            pvars = []
            for night in physical_nights:
                var = model.NewBoolVar(
                    f"physical__{activity_id}__w{week}__d{night}"
                )
                physical[activity_id, week, night] = var
                pvars.append(var)
            model.Add(sum(pvars) == s)

    # Workload conservation. Multiply by 2 so ECLO=1.5 is exact integer math.
    for activity_id, activity in activities.items():
        required_half_units = 2 * _as_int(
            activity.get("total_accesses"), f"{activity_id}.total_accesses"
        )
        delivered = sum(
            2 * normal[activity_id, week] + 3 * eclo[activity_id, week]
            for week in weeks
        )
        model.Add(delivered >= required_half_units)
        # Prevent pointless overscheduling while still allowing a 0.5-unit ECLO overshoot.
        model.Add(delivered <= required_half_units + 1)

    start_week: Dict[str, cp_model.IntVar] = {}
    end_week: Dict[str, cp_model.IntVar] = {}
    sentinel = horizon_weeks + 1

    for activity_id in activity_ids:
        start = model.NewIntVar(1, horizon_weeks, f"startweek__{activity_id}")
        end = model.NewIntVar(1, horizon_weeks, f"endweek__{activity_id}")
        start_week[activity_id] = start
        end_week[activity_id] = end

        start_candidates = []
        end_candidates = []
        for week in weeks:
            sc = model.NewIntVar(1, sentinel, f"startcand__{activity_id}__w{week}")
            ec = model.NewIntVar(0, horizon_weeks, f"endcand__{activity_id}__w{week}")
            model.Add(
                sc
                == week * scheduled[activity_id, week]
                + sentinel * (1 - scheduled[activity_id, week])
            )
            model.Add(ec == week * scheduled[activity_id, week])
            start_candidates.append(sc)
            end_candidates.append(ec)

        model.AddMinEquality(start, start_candidates)
        model.AddMaxEquality(end, end_candidates)

    for successor_id, activity in activities.items():
        predecessor_id = _clean(activity.get("predecessor_activity_id"))
        if predecessor_id:
            model.Add(start_week[successor_id] >= end_week[predecessor_id] + 1)

 
    activities_by_contract_type: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for activity_id, activity in activities.items():
        key = (
            activity_contract[activity_id],
            _clean(activity.get("activity_type")),
        )
        activities_by_contract_type[key].append(activity_id)

    # S4: rules 6 (weekly allocation) and 7 (workfronts) are enforced directly on the
    # PHYSICAL night variables, so the `access_night` we report is the night the
    # activity actually works. The old model had a second, independent set of
    # "access_night" booleans, which let a contract-week report fewer distinct
    # access_night values than it really used and let two activities sharing one
    # possession carry different access_night labels.
    contract_type_night_used: Dict[Tuple[str, str, int, int], cp_model.IntVar] = {}

    for (contract, activity_type), ids in activities_by_contract_type.items():
        project = projects[contract]
        cap = _as_int(
            project.get("number_of_maximum_access_per_week"),
            f"{contract}.number_of_maximum_access_per_week",
        )
        workfronts = _as_int(
            project.get("number_of_workfronts"),
            f"{contract}.number_of_workfronts",
        )
        for week in weeks:
            used_night_vars = []
            for night in physical_nights:
                members = [physical[activity_id, week, night] for activity_id in ids]

                # Rule 7: at most `number_of_workfronts` activities of this
                # contract+type on the same night.
                model.Add(sum(members) <= workfronts)

                used = model.NewBoolVar(
                    f"ctnight__{contract}__{activity_type}__w{week}__d{night}"
                )
                contract_type_night_used[contract, activity_type, week, night] = used
                for var in members:
                    model.Add(var <= used)
                model.Add(used <= sum(members))
                used_night_vars.append(used)

            # Rule 6: at most `number_of_maximum_access_per_week` distinct nights.
            model.Add(sum(used_night_vars) <= cap)


    location_night_used: Dict[Tuple[str, int, int], cp_model.IntVar] = {}
    excess_by_location_week: Dict[Tuple[str, int], cp_model.IntVar] = {}

    for location_id, nominal_supply in supply.items():
        ids = activities_at_location.get(location_id, [])
        if not ids:
            continue

        for week in weeks:
            used_vars = []
            for night in physical_nights:
                relevant = [physical[a, week, night] for a in ids]
                used = model.NewBoolVar(f"used__{location_id}__w{week}__d{night}")
                location_night_used[location_id, week, night] = used
                used_vars.append(used)

                for var in relevant:
                    model.Add(var <= used)
                model.Add(used <= sum(relevant))

                pm = [
                    physical[a, week, night]
                    for a in ids
                    if activity_access_type[a] == "PM"
                ]
                pc = [
                    physical[a, week, night]
                    for a in ids
                    if activity_access_type[a] == "PC"
                ]
                coworker = [
                    physical[a, week, night]
                    for a in ids
                    if activity_access_type[a] == "C"
                ]

                pm_sum = sum(pm) if pm else 0
                pc_sum = sum(pc) if pc else 0
                c_sum = sum(coworker) if coworker else 0

                # one PM alone, OR one PC + <=3 C, OR <=4 C
                model.Add(pm_sum <= 1)
                model.Add(pc_sum <= 1)
                model.Add(pm_sum + pc_sum <= 1)
                model.Add(c_sum + pc_sum + 4 * pm_sum <= 4)

            total_used = sum(used_vars)
            max_excess = max(0, PHYSICAL_NIGHTS_PER_WEEK - nominal_supply)
            excess = model.NewIntVar(
                0,
                max_excess,
                f"excess__{location_id}__w{week}",
            )
            model.Add(excess >= total_used - nominal_supply)
            model.Add(excess >= 0)
            model.Add(excess <= total_used)
            excess_by_location_week[location_id, week] = excess

            if scenario == "A":
                model.Add(total_used <= nominal_supply)
                model.Add(excess == 0)
            elif scenario == "C":
                model.Add(total_used <= nominal_supply + 1)
                model.Add(excess <= 1)
            # Scenario B intentionally permits additional location access nights.



    pair_conflicts = 0
    pair_coshare_exemptions = 0

    # NOTE (S8, not fixed here): this is O(n_activities^2 * weeks * nights) constraints.
    # At 54 activities it is fine (~156 pairs x 30 weeks x 7 nights). At ~108 activities
    # it becomes the bottleneck and Scenario A finds nothing inside 300 s. The fix is to
    # aggregate per (location, week, night) instead of per pair, or to skip weeks where
    # the two activities cannot both be active.
    for i, a in enumerate(activity_ids):
        for b in activity_ids[i + 1 :]:
            collision = closure[a] & closure[b]
            if not collision:
                continue

            if _co_share_pair_allowed(
                activity_access_type[a],
                activity_access_type[b],
                route[a],
                route[b],
                closure[a],
                closure[b],
            ):
                pair_coshare_exemptions += 1
                continue

            pair_conflicts += 1
            for week in weeks:
                for night in physical_nights:
                    model.Add(
                        physical[a, week, night] + physical[b, week, night] <= 1
                    )

    eclo_window_start: Dict[str, cp_model.IntVar] = {}
    if scenario == "C":
        all_lines = sorted({line for lines in affected_lines.values() for line in lines})
        for line in all_lines:
            eclo_window_start[line] = model.NewIntVar(
                1,
                max(1, horizon_weeks),
                f"eclo_window_start__{line}",
            )

        for activity_id in activity_ids:
            for week in weeks:
                e = eclo[activity_id, week]
                for line in affected_lines[activity_id]:
                    window = eclo_window_start[line]
                    model.Add(week >= window).OnlyEnforceIf(e)
                    model.Add(week <= window + 1).OnlyEnforceIf(e)

    contract_end_week: Dict[str, cp_model.IntVar] = {}
    contract_overrun_days: Dict[str, cp_model.IntVar] = {}

    activities_by_contract: Dict[str, List[str]] = defaultdict(list)
    for activity_id in activity_ids:
        activities_by_contract[activity_contract[activity_id]].append(activity_id)

    horizon_end_day = horizon_weeks * 7 - 1

    for contract, ids in activities_by_contract.items():
        end_var = model.NewIntVar(1, horizon_weeks, f"contract_end_week__{contract}")
        model.AddMaxEquality(end_var, [end_week[a] for a in ids])
        contract_end_week[contract] = end_var

        planned_date = _parse_date(
            projects[contract].get("planned_completion_date"),
            f"{contract}.planned_completion_date",
        )
        planned_day = _date_day_index(planned_date, horizon_start)

        overrun = model.NewIntVar(
            0,
            max(0, horizon_end_day - planned_day),
            f"contract_overrun_days__{contract}",
        )
        completion_day_expr = 7 * end_var - 1
        model.Add(overrun >= completion_day_expr - planned_day)
        model.Add(overrun >= 0)
        contract_overrun_days[contract] = overrun

        if scenario == "B":
            model.Add(completion_day_expr <= planned_day)
            model.Add(overrun == 0)

    activity_overrun_days: Dict[str, cp_model.IntVar] = {}
    for activity_id in activity_ids:
        contract = activity_contract[activity_id]
        planned_date = _parse_date(
            projects[contract].get("planned_completion_date"),
            f"{contract}.planned_completion_date",
        )
        planned_day = _date_day_index(planned_date, horizon_start)
        overrun = model.NewIntVar(
            0,
            max(0, horizon_end_day - planned_day),
            f"activity_overrun_days__{activity_id}",
        )
        model.Add(overrun >= 7 * end_week[activity_id] - 1 - planned_day)
        model.Add(overrun >= 0)
        activity_overrun_days[activity_id] = overrun


    objective_terms = []


    if scenario in {"A", "C"}:
        for activity_id, activity in activities.items():
            contract = activity_contract[activity_id]
            contract_priority = _as_int(
                projects[contract].get("contract_priority"),
                f"{contract}.contract_priority",
            )
            activity_priority = _as_int(
                activity.get("activity_priority"),
                f"{activity_id}.activity_priority",
            )
            base = PRIORITY_BASE_WEIGHT.get(contract_priority, 1)
            nudge = ACTIVITY_PRIORITY_TENTHS.get(activity_priority, 0)
            coefficient = base * (10 + nudge)
            objective_terms.append(coefficient * activity_overrun_days[activity_id])

    if scenario in {"B", "C"}:
        # 7 penalty per excess access-night -> x10 scale = 70.
        objective_terms.extend(70 * var for var in excess_by_location_week.values())
        # 5 penalty per ECLO night -> x10 scale = 50.
        objective_terms.extend(
            50 * eclo[activity_id, week]
            for activity_id in activity_ids
            for week in weeks
        )

    objective_terms.extend(
        scheduled[activity_id, week]
        for activity_id in activity_ids
        for week in weeks
    )

    model.Minimize(sum(objective_terms))


    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    # S6: default to a single search worker. Multi-worker CP-SAT is non-deterministic
    # (two identical runs produced different schedules with the same score), and the
    # judges need to be able to reproduce a submission byte for byte. Callers may still
    # raise this explicitly when they want raw speed over reproducibility.
    solver.parameters.num_search_workers = int(
        num_workers if num_workers is not None else DEFAULT_NUM_WORKERS
    )
    solver.parameters.random_seed = int(random_seed)
    solver.parameters.log_search_progress = False

    status_code = solver.Solve(model)
    status_name = solver.StatusName(status_code)

    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "status": "failure",
            "solver_status": status_name,
            "scenario": scenario,
            "schedule_access": [],
            "schedule_occupancy": [],
            "results": [],
            "capacity_usage": [],
            "warnings": warnings,
            "metrics": {
                "activities": len(activity_ids),
                "pair_conflicts": pair_conflicts,
                "pair_coshare_exemptions": pair_coshare_exemptions,
                "horizon_weeks": horizon_weeks,
                "horizon_start": horizon_start.isoformat(),
                "minimum_horizon_weeks": minimum_horizon_weeks,
            },
            "message": (
                f"CP-SAT returned {status_name} for scenario {scenario} with a "
                f"{horizon_weeks}-week horizon and a {time_limit_seconds:g}s limit. "
                "INFEASIBLE means the hard rules cannot all be met over that horizon; "
                "UNKNOWN means the time limit ran out before any schedule was found "
                "(raise --time-limit)."
            ),
        }


    schedule_access: List[Dict[str, Any]] = []
    chosen_physical_night: Dict[Tuple[str, int], int] = {}

    for activity_id in activity_ids:
        for week in weeks:
            if solver.Value(scheduled[activity_id, week]) != 1:
                continue
            chosen_physical_night[activity_id, week] = next(
                night
                for night in physical_nights
                if solver.Value(physical[activity_id, week, night]) == 1
            )

    # S4: `access_night` is a per (contract, activity_type, week) index into that
    # contract-type's granted nights (README 2.6). Rule 6 above caps the number of
    # distinct physical nights at `number_of_maximum_access_per_week`, so numbering the
    # nights actually used, in order, always lands inside 1..cap -- and two activities
    # working the same night always get the same label.
    nights_by_contract_type_week: Dict[Tuple[str, str, int], Set[int]] = defaultdict(set)
    for (activity_id, week), night in chosen_physical_night.items():
        key = (
            activity_contract[activity_id],
            _clean(activities[activity_id].get("activity_type")),
            week,
        )
        nights_by_contract_type_week[key].add(night)

    access_night_label: Dict[Tuple[str, str, int, int], int] = {}
    for (contract, activity_type, week), nights in nights_by_contract_type_week.items():
        for index, night in enumerate(sorted(nights), start=1):
            access_night_label[contract, activity_type, week, night] = index

    for activity_id in activity_ids:
        activity_type = _clean(activities[activity_id].get("activity_type"))
        contract = activity_contract[activity_id]
        seq = 0
        for week in weeks:
            if solver.Value(scheduled[activity_id, week]) != 1:
                continue
            seq += 1
            night = chosen_physical_night[activity_id, week]
            schedule_access.append(
                {
                    "activity_id": activity_id,
                    "access_seq": seq,
                    "week": week,
                    "eclo": int(solver.Value(eclo[activity_id, week])),
                    "access_night": access_night_label[
                        contract, activity_type, week, night
                    ],
                }
            )

 
    schedule_occupancy: List[Dict[str, Any]] = []
    for access in schedule_access:
        activity_id = str(access["activity_id"])
        week = int(access["week"])
        night = chosen_physical_night[activity_id, week]

        for location_id in sorted(route[activity_id]):
            schedule_occupancy.append(
                {
                    "activity_id": activity_id,
                    "week": week,
                    "location_id": location_id,
                    # Arbitrary label is allowed; using the internal physical night
                    # makes compatible same-night activities share the same group.
                    "co_share_group": f"b{night}",
                }
            )

    results_rows: List[Dict[str, Any]] = []
    for contract in sorted(projects):
        if contract not in contract_end_week:
            continue
        completion_week = int(solver.Value(contract_end_week[contract]))
        completion_date = _week_end_date(completion_week, horizon_start)
        planned_date = _parse_date(
            projects[contract].get("planned_completion_date"),
            f"{contract}.planned_completion_date",
        )
        overrun_days = max(0, (completion_date - planned_date).days)
        results_rows.append(
            {
                "scenario": scenario,
                "contract_number": contract,
                "simulated_completion_date": completion_date.isoformat(),
                "overrun_days": overrun_days,
            }
        )

    # Capacity heat-map feed for the frontend: how full every location-week actually is.
    # `used` counts distinct co_share_group labels, i.e. distinct possessions/nights,
    # which is exactly what rule 8 and the validator measure against supply_capacity.
    groups_by_location_week: Dict[Tuple[str, int], Set[str]] = defaultdict(set)
    for row in schedule_occupancy:
        groups_by_location_week[str(row["location_id"]), int(row["week"])].add(
            str(row["co_share_group"])
        )
    capacity_usage = [
        {
            "location_id": location_id,
            "week": week,
            "used": len(groups),
            "supply": supply.get(location_id, 0),
        }
        for (location_id, week), groups in sorted(groups_by_location_week.items())
        if groups
    ]

    # Useful debug metrics for the dashboard / explainability layer.
    total_eclo = sum(int(row["eclo"]) for row in schedule_access)
    total_excess = sum(
        int(solver.Value(var)) for var in excess_by_location_week.values()
    )
    predecessor_checks = []
    for activity_id, activity in activities.items():
        predecessor = _clean(activity.get("predecessor_activity_id"))
        if predecessor:
            predecessor_checks.append(
                {
                    "predecessor": predecessor,
                    "predecessor_last_week": int(solver.Value(end_week[predecessor])),
                    "successor": activity_id,
                    "successor_first_week": int(solver.Value(start_week[activity_id])),
                }
            )

    return {
        "status": "success",
        "solver_status": status_name,
        "scenario": scenario,
        "objective_value": float(solver.ObjectiveValue()),
        "schedule_access": schedule_access,
        "schedule_occupancy": schedule_occupancy,
        "results": results_rows,
        "capacity_usage": capacity_usage,
        "warnings": warnings,
        "metrics": {
            "activities": len(activity_ids),
            "access_rows": len(schedule_access),
            "occupancy_rows": len(schedule_occupancy),
            "eclo_nights_total": total_eclo,
            "excess_access_nights_total": total_excess,
            "pair_conflicts": pair_conflicts,
            "pair_coshare_exemptions": pair_coshare_exemptions,
            "wall_time_seconds": float(solver.WallTime()),
            "horizon_weeks": horizon_weeks,
            "horizon_start": horizon_start.isoformat(),
            "minimum_horizon_weeks": minimum_horizon_weeks,
        },
        "predecessor_checks": predecessor_checks,
        "debug": {
            "horizon_start": horizon_start.isoformat(),
            "horizon_weeks": horizon_weeks,
            "official_horizon_weeks": official_horizon_weeks,
            "physical_nights_per_week": PHYSICAL_NIGHTS_PER_WEEK,
            "interchange_stations": sorted(interchange_stations),
            "shared_sectors": sorted(shared_sector_bases),
        },
    }


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="NebulaX PS1 OR-Tools railway access solver"
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Folder containing 01_LINES.csv ... 08_ACTIVITY_DETAILS.csv",
    )
    parser.add_argument(
        "--scenario",
        choices=["A", "B", "C", "a", "b", "c"],
        default="A",
    )
    parser.add_argument(
        "--output-dir",
        default="submission",
        help="Folder to write the three submission CSVs",
    )
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()

    data = load_instance(args.data_dir)
    result = solve_schedule(
        data,
        args.scenario,
        time_limit_seconds=args.time_limit,
        num_workers=args.workers,
    )

    print(f"status        : {result['status']}")
    print(f"solver_status : {result['solver_status']}")
    print(f"scenario      : {result['scenario']}")

    if result["status"] != "success":
        print(result.get("message", "Solver failed"))
        raise SystemExit(2)

    if result.get("horizon_extended_to"):
        print(f"horizon       : extended to {result['horizon_extended_to']} weeks")
    for warning in result.get("warnings", []):
        print(f"warning       : {warning}")

    files = write_submission(result, args.output_dir)
    print(f"objective     : {result['objective_value']}")
    print(f"metrics       : {result['metrics']}")
    print("predecessors  :")
    for check in result["predecessor_checks"]:
        print(
            "  "
            f"{check['predecessor']} ends w{check['predecessor_last_week']} -> "
            f"{check['successor']} starts w{check['successor_first_week']}"
        )
    print("files         :")
    for name, path in files.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    _main()
