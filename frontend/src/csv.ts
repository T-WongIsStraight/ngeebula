// Reading the 8 input CSVs in the browser, checking they are all there, and summarising them.

import type { Contract, Activity, Location } from "./types";

// The 8 files the judges upload, with the columns each one must have.
export const REQUIRED_FILES: { name: string; key: InstanceKey; columns: string[] }[] = [
  { name: "01_LINES.csv", key: "lines", columns: ["line_code", "line_name"] },
  { name: "02_STATIONS.csv", key: "stations", columns: ["station_id", "line_code", "seq", "is_interchange"] },
  { name: "03_SECTORS.csv", key: "sectors", columns: ["sector_id", "line_code", "from_station_id", "to_station_id"] },
  { name: "04_LOCATION_SUPPLY.csv", key: "locations", columns: ["location_id", "location_kind", "line_code", "bound", "supply_capacity"] },
  { name: "05_BUFFER_LOCATION.csv", key: "buffers", columns: ["nature_of_works", "up_to_buffer_sectors", "opposite_bound_required"] },
  { name: "06_PARAMETERS.csv", key: "params", columns: ["key", "value"] },
  { name: "07_PROJECT_DETAILS.csv", key: "contracts", columns: ["contract_number", "contract_priority", "planned_completion_date", "number_of_workfronts", "access_type", "number_of_maximum_access_per_week"] },
  { name: "08_ACTIVITY_DETAILS.csv", key: "activities", columns: ["activity_id", "contract_number", "start_location_id", "end_location_id", "total_accesses", "planned_start_date"] },
];

export type InstanceKey = "lines" | "stations" | "sectors" | "locations" | "buffers" | "params" | "contracts" | "activities";
type Row = Record<string, string>;

// Everything from the 8 files, as plain rows
export type Instance = {
  lines: Row[];
  stations: Row[];
  sectors: Row[];
  locations: Location[];
  buffers: Row[];
  params: Row[];
  contracts: Contract[];
  activities: Activity[];
};

// One line per file: found or not, and what is wrong if anything
export type FileCheck = { name: string; status: "ok" | "missing" | "bad"; detail: string };

// "a,b,c\n1,2,3" -> [{a:"1", b:"2", c:"3"}]
export function parseCsv(text: string): Row[] {
  const lines = text.replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim() !== "");
  if (lines.length === 0) return [];
  const keys = lines[0].split(",").map((k) => k.trim());
  return lines.slice(1).map((l) => {
    const v = l.split(",");
    return Object.fromEntries(keys.map((k, i) => [k, (v[i] ?? "").trim()]));
  });
}

// Read the chosen files, match them to the 8 required names, check columns.
export async function readInstanceFiles(files: File[]): Promise<{ checks: FileCheck[]; instance: Instance | null }> {
  const byName = new Map(files.map((f) => [f.name, f]));
  const checks: FileCheck[] = [];
  const parts: Partial<Record<InstanceKey, Row[]>> = {};

  for (const req of REQUIRED_FILES) {
    const f = byName.get(req.name);
    if (!f) { checks.push({ name: req.name, status: "missing", detail: "not selected" }); continue; }
    const rows = parseCsv(await f.text());
    const have = rows.length ? Object.keys(rows[0]) : [];
    const missingCols = req.columns.filter((c) => !have.includes(c));
    if (rows.length === 0) checks.push({ name: req.name, status: "bad", detail: "file is empty" });
    else if (missingCols.length) checks.push({ name: req.name, status: "bad", detail: `missing column ${missingCols[0]}` });
    else { checks.push({ name: req.name, status: "ok", detail: `${rows.length} rows` }); parts[req.key] = rows; }
  }

  const allOk = checks.every((c) => c.status === "ok");
  return { checks, instance: allOk ? (parts as unknown as Instance) : null };
}

// The numbers a controller wants to see before pressing Build.
export type InstanceSummary = {
  horizonStart: string;
  horizonEnd: string;
  weeks: number;
  lines: number;
  stations: number;
  hubs: number;
  tunnels: number;
  spots: number;
  contracts: number;
  jobs: number;
  nightsNeeded: number;
  nightsPerWeek: number;
  nightsAvailable: number;
  priority1: number;
};

export function summarise(inst: Instance): InstanceSummary {
  const param = (k: string) => inst.params.find((p) => p.key === k)?.value ?? "";
  const horizonStart = param("horizon_start");
  const weeks = Number(param("horizon_weeks")) || 0;
  const [y, m, d] = horizonStart.split("-").map(Number);
  const end = new Date(Date.UTC(y, m - 1, d + weeks * 7 - 1));
  const nightsPerWeek = inst.locations.reduce((s, l) => s + Number(l.supply_capacity), 0);
  return {
    horizonStart,
    horizonEnd: isNaN(end.getTime()) ? "?" : end.toISOString().slice(0, 10),
    weeks,
    lines: inst.lines.length,
    stations: new Set(inst.stations.map((s) => s.station_id)).size,
    hubs: new Set(inst.stations.filter((s) => s.is_interchange === "1").map((s) => s.station_id)).size,
    tunnels: inst.sectors.length,
    spots: inst.locations.length,
    contracts: inst.contracts.length,
    jobs: inst.activities.length,
    nightsNeeded: inst.activities.reduce((s, a) => s + Number(a.total_accesses), 0),
    nightsPerWeek,
    nightsAvailable: nightsPerWeek * weeks,
    priority1: inst.contracts.filter((c) => c.contract_priority === "1").length,
  };
}
