// Presentation helpers for the two grids and the explain panel.
//
// NOTHING here scores, validates or schedules anything. Every number shown in the
// UI comes from the backend (result.results, result.report, result.capacity_usage,
// result.explanations). The functions below only re-shape what the backend sent:
// readable names, week/date labels, and lookup maps.
//
// The other agent owns src/lib/dates.ts; these date helpers are deliberately local
// so the two files never have to agree.

import type {
  Activity,
  CapacityUsage,
  Contract,
  AccessRow,
  Location,
  OccupancyRow,
  ResultRow,
  SolveResult,
} from "../types";

const DAY_MS = 86_400_000;

/** Backend numbers may arrive as numbers or strings. */
export function num(value: number | string | null | undefined): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

/* ------------------------------------------------------------------ dates */

/** Parse an ISO "YYYY-MM-DD" as UTC midnight, so no timezone can shift the day. */
export function parseISO(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? "");
  if (!m) return null;
  return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
}

/** Monday of week N: horizon_start + 7 * (N - 1). */
export function weekStart(horizonStart: string, week: number): Date | null {
  const base = parseISO(horizonStart);
  if (!base) return null;
  return new Date(base.getTime() + (week - 1) * 7 * DAY_MS);
}

/** Sunday ending week N: horizon_start + 7 * N - 1 day. */
export function weekEnd(horizonStart: string, week: number): Date | null {
  const start = weekStart(horizonStart, week);
  if (!start) return null;
  return new Date(start.getTime() + 6 * DAY_MS);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "05 Jan 2027" — short, unambiguous, no locale surprises. */
export function fmtDate(d: Date | null): string {
  if (!d) return "?";
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${day} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** "05 Jan" — for the tight column headers. */
export function fmtDayMonth(d: Date | null): string {
  if (!d) return "?";
  return `${String(d.getUTCDate()).padStart(2, "0")} ${MONTHS[d.getUTCMonth()]}`;
}

/** "week 12 (15 Mar 2027 – 21 Mar 2027)" */
export function weekRangeLabel(horizonStart: string, week: number): string {
  return `week ${week} (${fmtDate(weekStart(horizonStart, week))} – ${fmtDate(weekEnd(horizonStart, week))})`;
}

/** Which week contains a date (1-based). null when the date is unusable. */
export function weekOfDate(horizonStart: string, iso: string | null | undefined): number | null {
  const base = parseISO(horizonStart);
  const d = iso ? parseISO(iso) : null;
  if (!base || !d) return null;
  return Math.floor((d.getTime() - base.getTime()) / (7 * DAY_MS)) + 1;
}

/* -------------------------------------------------------- location naming */

export type ParsedLocation = {
  kind: "SEC" | "PLAT" | "other";
  line: string;
  bound: string;
  /** stations this location touches, in id form */
  stations: string[];
};

/** "SEC:ALP:S02_S03:EB" and "PLAT:ALP:S03:EB" -> parts. Unknown shapes degrade gracefully. */
export function parseLocation(locationId: string): ParsedLocation {
  const parts = (locationId ?? "").split(":");
  const tag = parts[0] ?? "";
  const line = parts[1] ?? "";
  const body = parts[2] ?? "";
  const bound = parts[3] ?? "";
  if (tag === "SEC") {
    const stations = body.split("_").filter(Boolean);
    return { kind: "SEC", line, bound, stations };
  }
  if (tag === "PLAT") {
    return { kind: "PLAT", line, bound, stations: body ? [body] : [] };
  }
  return { kind: "other", line, bound, stations: [] };
}

/** Line name if the instance carried one, otherwise the code itself. */
export function lineLabel(code: string, lineNames?: Record<string, string>): string {
  return lineNames?.[code] ?? code;
}

/** "S02–S03 EB" / "Platform S03 EB". Never invents names that are not in the id. */
export function locationLabel(locationId: string): string {
  const p = parseLocation(locationId);
  if (p.kind === "SEC") return `${p.stations.join("–")} ${p.bound}`.trim();
  if (p.kind === "PLAT") return `Platform ${p.stations[0] ?? ""} ${p.bound}`.trim();
  return locationId;
}

/** Same, but says which line it is on — for panels where the row grouping is gone. */
export function locationLabelWithLine(locationId: string, lineNames?: Record<string, string>): string {
  const p = parseLocation(locationId);
  if (p.kind === "other") return locationId;
  return `${locationLabel(locationId)} · ${lineLabel(p.line, lineNames)}`;
}

/** "tunnel sector" -> "tunnels", anything else -> "station platforms". */
export function kindLabel(locationKind: string): string {
  return /tunnel/i.test(locationKind) ? "tunnels" : "station platforms";
}

/* ---------------------------------------------------------------- indexing */

export type GridIndex = {
  horizonStart: string;
  lineNames: Record<string, string>;
  contractById: Map<string, Contract>;
  activityById: Map<string, Activity>;
  activitiesByContract: Map<string, Activity[]>;
  resultByContract: Map<string, ResultRow>;
  /** access rows for one activity, ascending by week */
  accessByActivity: Map<string, AccessRow[]>;
  /** "A001|22" -> that night */
  accessByActivityWeek: Map<string, AccessRow>;
  /** first and last week an activity actually works */
  spanByActivity: Map<string, [number, number]>;
  /** first and last week any of a contract's activities works */
  spanByContract: Map<string, [number, number]>;
  occupancyByActivity: Map<string, OccupancyRow[]>;
  /** "SEC:ALP:S01_S02:EB|12" -> rows booked there that week */
  occupancyByCell: Map<string, OccupancyRow[]>;
  /** same key -> the backend's used/supply for that cell */
  usageByCell: Map<string, CapacityUsage>;
  /** stations that appear on more than one line (interchanges) */
  hubStations: Set<string>;
  /** locations that sit on a hub station (or, failing that, the lowest-supply ones) */
  hubLocations: Set<string>;
  minSupply: number;
};

export function cellKey(locationId: string, week: number | string): string {
  return `${locationId}|${num(week)}`;
}

export function activityWeekKey(activityId: string, week: number | string): string {
  return `${activityId}|${num(week)}`;
}

function push<K, V>(map: Map<K, V[]>, key: K, value: V): void {
  const list = map.get(key);
  if (list) list.push(value);
  else map.set(key, [value]);
}

/** Line names only exist on some instances; read them if they are there. */
function readLineNames(instance: SolveResult["instance"]): Record<string, string> {
  const carrier = instance as unknown as { lines?: Array<{ line_code?: string; line_name?: string }> };
  const out: Record<string, string> = {};
  for (const line of carrier.lines ?? []) {
    if (line?.line_code && line?.line_name) out[line.line_code] = line.line_name;
  }
  return out;
}

/** One pass over the payload; everything the three components look up lives here. */
export function buildIndex(result: SolveResult): GridIndex {
  const inst = result.instance;

  const contractById = new Map<string, Contract>();
  for (const c of inst.contracts ?? []) contractById.set(c.contract_number, c);

  const activityById = new Map<string, Activity>();
  const activitiesByContract = new Map<string, Activity[]>();
  for (const a of inst.activities ?? []) {
    activityById.set(a.activity_id, a);
    push(activitiesByContract, a.contract_number, a);
  }

  const resultByContract = new Map<string, ResultRow>();
  for (const r of result.results ?? []) resultByContract.set(r.contract_number, r);

  const accessByActivity = new Map<string, AccessRow[]>();
  const accessByActivityWeek = new Map<string, AccessRow>();
  const spanByActivity = new Map<string, [number, number]>();
  for (const row of result.schedule_access ?? []) {
    const week = num(row.week);
    push(accessByActivity, row.activity_id, row);
    accessByActivityWeek.set(activityWeekKey(row.activity_id, week), row);
    const span = spanByActivity.get(row.activity_id);
    spanByActivity.set(
      row.activity_id,
      span ? [Math.min(span[0], week), Math.max(span[1], week)] : [week, week],
    );
  }
  for (const rows of accessByActivity.values()) rows.sort((a, b) => num(a.week) - num(b.week));

  const spanByContract = new Map<string, [number, number]>();
  for (const [activityId, span] of spanByActivity) {
    const contract = activityById.get(activityId)?.contract_number;
    if (!contract) continue;
    const current = spanByContract.get(contract);
    spanByContract.set(
      contract,
      current ? [Math.min(current[0], span[0]), Math.max(current[1], span[1])] : [span[0], span[1]],
    );
  }

  const occupancyByActivity = new Map<string, OccupancyRow[]>();
  const occupancyByCell = new Map<string, OccupancyRow[]>();
  for (const row of result.schedule_occupancy ?? []) {
    push(occupancyByActivity, row.activity_id, row);
    push(occupancyByCell, cellKey(row.location_id, row.week), row);
  }

  const usageByCell = new Map<string, CapacityUsage>();
  for (const u of result.capacity_usage ?? []) usageByCell.set(cellKey(u.location_id, u.week), u);

  // Hubs, from the data only: a station that appears under more than one line_code.
  const linesPerStation = new Map<string, Set<string>>();
  for (const s of inst.sectors ?? []) {
    for (const station of [s.from_station_id, s.to_station_id]) {
      if (!station) continue;
      const set = linesPerStation.get(station) ?? new Set<string>();
      set.add(s.line_code);
      linesPerStation.set(station, set);
    }
  }
  const hubStations = new Set<string>();
  for (const [station, lines] of linesPerStation) if (lines.size > 1) hubStations.add(station);

  const supplies = (inst.locations ?? []).map((l) => num(l.supply_capacity));
  const minSupply = supplies.length ? Math.min(...supplies) : 0;

  const hubLocations = new Set<string>();
  for (const l of inst.locations ?? []) {
    const touchesHub = parseLocation(l.location_id).stations.some((s) => hubStations.has(s));
    // Fallback when an instance has no shared stations at all: the tightest rows.
    const tightest = hubStations.size === 0 && num(l.supply_capacity) === minSupply;
    if (touchesHub || tightest) hubLocations.add(l.location_id);
  }

  return {
    horizonStart: inst.horizon_start,
    lineNames: readLineNames(inst),
    contractById,
    activityById,
    activitiesByContract,
    resultByContract,
    accessByActivity,
    accessByActivityWeek,
    spanByActivity,
    spanByContract,
    occupancyByActivity,
    occupancyByCell,
    usageByCell,
    hubStations,
    hubLocations,
    minSupply,
  };
}

/* ------------------------------------------------------------- small bits */

/** Contracts sorted the way a controller reads them: most important first. */
export function sortedContracts(contracts: Contract[]): Contract[] {
  return [...contracts].sort(
    (a, b) =>
      num(a.contract_priority) - num(b.contract_priority) ||
      a.contract_number.localeCompare(b.contract_number),
  );
}

/** "on time" / "3 days late" — straight from RESULTS.csv, never recomputed. */
export function lateLabel(row: ResultRow | undefined): { late: number; text: string } {
  const late = num(row?.overrun_days);
  return { late, text: late > 0 ? `${late} ${late === 1 ? "day" : "days"} late` : "on time" };
}

/** 0 empty · 1 some room · 2 nearly full · 3 full · 4 over the limit. */
export function heatLevel(used: number, supply: number): 0 | 1 | 2 | 3 | 4 {
  if (used <= 0) return 0;
  if (supply <= 0) return 4;
  if (used > supply) return 4;
  if (used === supply) return 3;
  return used / supply >= 0.5 ? 2 : 1;
}

export const HEAT_WORDS = ["empty", "some room", "nearly full", "full", "over the limit"] as const;

/** Rows grouped for the heat-map: line, then tunnels before platforms. */
export function groupLocations(
  locations: Location[],
  lineNames?: Record<string, string>,
): { key: string; title: string; rows: Location[] }[] {
  const groups = new Map<string, { key: string; title: string; rows: Location[] }>();
  for (const l of locations) {
    const tunnel = /tunnel/i.test(l.location_kind);
    const key = `${l.line_code}|${tunnel ? "0" : "1"}`;
    const group = groups.get(key) ?? {
      key,
      title: `Line ${lineLabel(l.line_code, lineNames)} · ${kindLabel(l.location_kind)}`,
      rows: [],
    };
    group.rows.push(l);
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => a.key.localeCompare(b.key));
}
