"""Presentation helpers for the two grids and the explain panel.

NOTHING here scores, validates or schedules anything. Every number shown in the
UI comes from the backend payload (``result["results"]``, ``result["report"]``,
``result["capacity_usage"]``, ``result["explanations"]``). The functions below
only re-shape what the backend sent: readable names, week/date labels and
lookup maps.

This is the Python twin of ``frontend/src/lib/grid.ts`` — same words, same
rules, so the Streamlit app and the React app describe the schedule the same
way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

Row = Mapping[str, Any]

# --------------------------------------------------------------- coercion


def num(value: Any) -> int:
    """Backend numbers may arrive as int or str. Everything we show is whole."""
    if value is None or value is True or value is False:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def text(value: Any) -> str:
    """A safe string for labels: ``None`` becomes an empty string."""
    return "" if value is None else str(value)


def rows(result: Mapping[str, Any], key: str) -> list[Row]:
    """A list of dict rows from the payload, never ``None``."""
    value = result.get(key)
    return list(value) if isinstance(value, list) else []


# ------------------------------------------------------------------ dates

_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def parse_iso(value: Any) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` prefix. Anything else returns ``None``."""
    raw = text(value).strip()
    if len(raw) < 10:
        return None
    try:
        return date(int(raw[0:4]), int(raw[5:7]), int(raw[8:10]))
    except ValueError:
        return None


def week_start(horizon_start: Any, week: Any) -> date | None:
    """Monday of week N: ``horizon_start + 7 * (N - 1)``."""
    base = parse_iso(horizon_start)
    if base is None:
        return None
    return base + timedelta(days=7 * (num(week) - 1))


def week_end(horizon_start: Any, week: Any) -> date | None:
    """Sunday ending week N: ``horizon_start + 7 * N - 1 day``."""
    start = week_start(horizon_start, week)
    return None if start is None else start + timedelta(days=6)


def fmt_date(value: date | None) -> str:
    """``05 Jan 2027`` — short, unambiguous, no locale surprises."""
    if value is None:
        return "?"
    return f"{value.day:02d} {_MONTHS[value.month - 1]} {value.year}"


def fmt_day_month(value: date | None) -> str:
    """``05 Jan`` — for the tight column headers."""
    if value is None:
        return "?"
    return f"{value.day:02d} {_MONTHS[value.month - 1]}"


def week_range_label(horizon_start: Any, week: Any) -> str:
    """``week 12 (15 Mar 2027 - 21 Mar 2027)``."""
    w = num(week)
    return (
        f"week {w} ({fmt_date(week_start(horizon_start, w))}"
        f" – {fmt_date(week_end(horizon_start, w))})"
    )


def week_of_date(horizon_start: Any, iso: Any) -> int | None:
    """Which week contains a date (1-based). ``None`` when unusable."""
    base = parse_iso(horizon_start)
    target = parse_iso(iso)
    if base is None or target is None:
        return None
    return (target - base).days // 7 + 1


# -------------------------------------------------------- location naming


_EN_DASH = "–"


@dataclass(frozen=True)
class ParsedLocation:
    kind: str  # "SEC" | "PLAT" | "other"
    line: str
    bound: str
    stations: tuple[str, ...]


def parse_location(location_id: Any) -> ParsedLocation:
    """``SEC:ALP:S02_S03:EB`` / ``PLAT:ALP:S03:EB`` -> parts.

    Unknown shapes degrade gracefully instead of raising: hidden instances may
    name things differently.
    """
    parts = text(location_id).split(":")
    tag = parts[0] if len(parts) > 0 else ""
    line = parts[1] if len(parts) > 1 else ""
    body = parts[2] if len(parts) > 2 else ""
    bound = parts[3] if len(parts) > 3 else ""
    if tag == "SEC":
        return ParsedLocation("SEC", line, bound, tuple(p for p in body.split("_") if p))
    if tag == "PLAT":
        return ParsedLocation("PLAT", line, bound, (body,) if body else ())
    return ParsedLocation("other", line, bound, ())


def line_label(code: Any, line_names: Mapping[str, str] | None = None) -> str:
    """Line name if the instance carried one, otherwise the code itself."""
    code_s = text(code)
    if line_names:
        return line_names.get(code_s, code_s)
    return code_s


def location_label(location_id: Any) -> str:
    """``S02-S03 EB`` / ``Platform S03 EB``. Never invents names."""
    p = parse_location(location_id)
    if p.kind == "SEC":
        return f"{_EN_DASH.join(p.stations)} {p.bound}".strip()
    if p.kind == "PLAT":
        first = p.stations[0] if p.stations else ""
        return f"Platform {first} {p.bound}".strip()
    return text(location_id)


def location_label_with_line(
    location_id: Any, line_names: Mapping[str, str] | None = None
) -> str:
    """Same, but says which line it is on."""
    p = parse_location(location_id)
    if p.kind == "other":
        return text(location_id)
    return f"{location_label(location_id)} · {line_label(p.line, line_names)}"


def kind_label(location_kind: Any) -> str:
    """``tunnel sector`` -> ``tunnels``, anything else -> ``station platforms``."""
    return "tunnels" if "tunnel" in text(location_kind).lower() else "station platforms"


# ---------------------------------------------------------------- indexing


def cell_key(location_id: Any, week: Any) -> str:
    return f"{text(location_id)}|{num(week)}"


def activity_week_key(activity_id: Any, week: Any) -> str:
    return f"{text(activity_id)}|{num(week)}"


@dataclass
class GridIndex:
    """One pass over the payload; everything the three views look up lives here."""

    horizon_start: str = ""
    horizon_weeks: int = 0
    line_names: dict[str, str] = field(default_factory=dict)
    contract_by_id: dict[str, Row] = field(default_factory=dict)
    activity_by_id: dict[str, Row] = field(default_factory=dict)
    activities_by_contract: dict[str, list[Row]] = field(default_factory=dict)
    result_by_contract: dict[str, Row] = field(default_factory=dict)
    #: access rows for one activity, ascending by week
    access_by_activity: dict[str, list[Row]] = field(default_factory=dict)
    #: "A001|22" -> that night
    access_by_activity_week: dict[str, Row] = field(default_factory=dict)
    #: first and last week an activity actually works
    span_by_activity: dict[str, tuple[int, int]] = field(default_factory=dict)
    #: first and last week any of a contract's activities works
    span_by_contract: dict[str, tuple[int, int]] = field(default_factory=dict)
    occupancy_by_activity: dict[str, list[Row]] = field(default_factory=dict)
    #: "SEC:ALP:S01_S02:EB|12" -> rows booked there that week
    occupancy_by_cell: dict[str, list[Row]] = field(default_factory=dict)
    #: same key -> the backend's used/supply for that cell
    usage_by_cell: dict[str, Row] = field(default_factory=dict)
    #: stations that appear on more than one line_code (interchanges)
    hub_stations: set[str] = field(default_factory=set)
    #: locations sitting on a hub station (or, failing that, the tightest rows)
    hub_locations: set[str] = field(default_factory=set)
    min_supply: int = 0


def _push(store: dict[str, list[Row]], key: str, value: Row) -> None:
    store.setdefault(key, []).append(value)


def _read_line_names(instance: Mapping[str, Any]) -> dict[str, str]:
    """Line names only exist on some instances; read them if they are there."""
    out: dict[str, str] = {}
    lines = instance.get("lines")
    if isinstance(lines, list):
        for line in lines:
            if not isinstance(line, Mapping):
                continue
            code, name = text(line.get("line_code")), text(line.get("line_name"))
            if code and name:
                out[code] = name
    return out


def build_index(result: Mapping[str, Any]) -> GridIndex:
    """Build every lookup the three views need, from the payload alone."""
    instance = result.get("instance")
    instance = instance if isinstance(instance, Mapping) else {}

    idx = GridIndex(
        horizon_start=text(instance.get("horizon_start")),
        horizon_weeks=num(instance.get("horizon_weeks")),
        line_names=_read_line_names(instance),
    )

    for contract in rows(instance, "contracts"):
        idx.contract_by_id[text(contract.get("contract_number"))] = contract

    for activity in rows(instance, "activities"):
        activity_id = text(activity.get("activity_id"))
        idx.activity_by_id[activity_id] = activity
        _push(idx.activities_by_contract, text(activity.get("contract_number")), activity)

    for row in rows(result, "results"):
        idx.result_by_contract[text(row.get("contract_number"))] = row

    for row in rows(result, "schedule_access"):
        activity_id = text(row.get("activity_id"))
        week = num(row.get("week"))
        _push(idx.access_by_activity, activity_id, row)
        idx.access_by_activity_week[activity_week_key(activity_id, week)] = row
        span = idx.span_by_activity.get(activity_id)
        idx.span_by_activity[activity_id] = (
            (min(span[0], week), max(span[1], week)) if span else (week, week)
        )
    for nights in idx.access_by_activity.values():
        nights.sort(key=lambda r: num(r.get("week")))

    for activity_id, span in idx.span_by_activity.items():
        activity = idx.activity_by_id.get(activity_id)
        contract = text(activity.get("contract_number")) if activity else ""
        if not contract:
            continue
        current = idx.span_by_contract.get(contract)
        idx.span_by_contract[contract] = (
            (min(current[0], span[0]), max(current[1], span[1])) if current else span
        )

    for row in rows(result, "schedule_occupancy"):
        _push(idx.occupancy_by_activity, text(row.get("activity_id")), row)
        _push(idx.occupancy_by_cell, cell_key(row.get("location_id"), row.get("week")), row)

    for row in rows(result, "capacity_usage"):
        idx.usage_by_cell[cell_key(row.get("location_id"), row.get("week"))] = row

    # Hubs, from the data only: a station that appears under more than one line_code.
    lines_per_station: dict[str, set[str]] = {}
    for sector in rows(instance, "sectors"):
        for station in (sector.get("from_station_id"), sector.get("to_station_id")):
            station_id = text(station)
            if station_id:
                lines_per_station.setdefault(station_id, set()).add(text(sector.get("line_code")))
    idx.hub_stations = {s for s, lines in lines_per_station.items() if len(lines) > 1}

    locations = rows(instance, "locations")
    supplies = [num(loc.get("supply_capacity")) for loc in locations]
    idx.min_supply = min(supplies) if supplies else 0

    for loc in locations:
        location_id = text(loc.get("location_id"))
        touches_hub = any(s in idx.hub_stations for s in parse_location(location_id).stations)
        # Fallback when an instance has no shared stations at all: the tightest rows.
        tightest = not idx.hub_stations and num(loc.get("supply_capacity")) == idx.min_supply
        if touches_hub or tightest:
            idx.hub_locations.add(location_id)

    return idx


# ------------------------------------------------------------- small bits


def sorted_contracts(contracts: Iterable[Row]) -> list[Row]:
    """Contracts sorted the way a controller reads them: most important first."""
    return sorted(
        contracts,
        key=lambda c: (num(c.get("contract_priority")), text(c.get("contract_number"))),
    )


def late_label(row: Row | None) -> tuple[int, str]:
    """``(days, "on time" | "3 days late")`` — straight from RESULTS.csv."""
    late = num(row.get("overrun_days")) if row else 0
    if late <= 0:
        return 0, "on time"
    return late, f"{late} {'day' if late == 1 else 'days'} late"


def heat_level(used: int, supply: int) -> int:
    """0 empty - 1 some room - 2 nearly full - 3 full - 4 over the limit."""
    if used <= 0:
        return 0
    if supply <= 0:
        return 4
    if used > supply:
        return 4
    if used == supply:
        return 3
    return 2 if used / supply >= 0.5 else 1


HEAT_WORDS = ("empty", "some room", "nearly full", "full", "over the limit")

#: Extra glyphs so "full" and "over" are never colour-only.
HEAT_GLYPH = {3: "◼", 4: "▲"}

#: Priority colours. Mid-dark hues so they read on a light AND a dark page,
#: and so white glyph text on top of them stays legible.
PRIORITY_COLOR = {1: "#C13F4E", 2: "#B5761F", 3: "#3F72B0"}
PRIORITY_FALLBACK = "#6B7280"

#: One colour per heat level, in the same order as HEAT_WORDS.
HEAT_COLORS = (
    "rgba(136,142,150,0.20)",  # 0 empty
    "#3F72B0",                 # 1 some room
    "#B5761F",                 # 2 nearly full
    "#C0492F",                 # 3 full
    "#8E2038",                 # 4 over the limit
)

DEADLINE_COLOR = "#7C5CD6"
WAITING_COLOR = "#8A9199"


def priority_color(priority: Any) -> str:
    return PRIORITY_COLOR.get(num(priority), PRIORITY_FALLBACK)


def group_locations(
    locations: Sequence[Row], line_names: Mapping[str, str] | None = None
) -> list[tuple[str, str, list[Row]]]:
    """Rows grouped for the heat-map: line, then tunnels before platforms.

    Returns ``[(sort_key, title, rows), ...]``.
    """
    groups: dict[str, tuple[str, list[Row]]] = {}
    for loc in locations:
        is_tunnel = "tunnel" in text(loc.get("location_kind")).lower()
        key = f"{text(loc.get('line_code'))}|{'0' if is_tunnel else '1'}"
        title = (
            f"Line {line_label(loc.get('line_code'), line_names)}"
            f" · {kind_label(loc.get('location_kind'))}"
        )
        groups.setdefault(key, (title, []))[1].append(loc)
    return [(key, title, members) for key, (title, members) in sorted(groups.items())]


def unique_labels(labels: Sequence[str]) -> list[str]:
    """Plotly categorical axes need distinct labels; pad repeats invisibly."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for label in labels:
        count = seen.get(label, 0)
        seen[label] = count + 1
        out.append(label + "​" * count)
    return out
