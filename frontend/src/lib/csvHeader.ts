// The ONLY client-side check on an upload: is this file one of the 8, and does
// its header row carry the columns the backend needs (CLAUDE.md §4)?
// Nothing here parses the schedule or judges it; the solver does that.

/** Columns every file must have. Extra columns are fine and are ignored. */
export const EXPECTED_COLUMNS: Record<string, string[]> = {
  "01_LINES.csv": ["line_code", "line_name"],
  "02_STATIONS.csv": ["station_id", "line_code", "seq", "is_interchange"],
  "03_SECTORS.csv": ["sector_id", "line_code", "from_station_id", "to_station_id", "seq", "is_shared"],
  "04_LOCATION_SUPPLY.csv": ["location_id", "location_kind", "line_code", "bound", "supply_capacity"],
  "05_BUFFER_LOCATION.csv": ["nature_of_works", "up_to_buffer_sectors", "opposite_bound_required"],
  "06_PARAMETERS.csv": ["key", "value"],
  "07_PROJECT_DETAILS.csv": [
    "contract_number",
    "contract_description",
    "contract_award_date",
    "activity_type",
    "nature_of_activity",
    "contract_priority",
    "contract_completion_date",
    "planned_completion_date",
    "number_of_workfronts",
    "access_type",
    "number_of_maximum_access_per_week",
  ],
  "08_ACTIVITY_DETAILS.csv": [
    "activity_id",
    "contract_number",
    "activity_type",
    "start_location_id",
    "end_location_id",
    "total_accesses",
    "planned_start_date",
    "predecessor_activity_id",
    "activity_priority",
  ],
};

/** Split one CSV line, honouring "quoted, fields" and doubled "" escapes. */
export function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i++;
        } else quoted = false;
      } else cur += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out.map((c) => c.trim().replace(/^﻿/, ""));
}

/** Read the first line of a File without loading the whole thing. */
export async function readHeader(file: File): Promise<string[]> {
  const head = await file.slice(0, 8192).text();
  const firstLine = head.split(/\r?\n/, 1)[0] ?? "";
  return splitCsvLine(firstLine).map((c) => c.toLowerCase());
}

export type HeaderCheck = { ok: boolean; missingColumns: string[] };

/**
 * Compare a file's header row with the columns expected for its name.
 * An unknown file name is reported as ok:false with no missing columns.
 */
export async function checkHeader(file: File): Promise<HeaderCheck> {
  const expected = EXPECTED_COLUMNS[canonicalName(file.name)];
  if (!expected) return { ok: false, missingColumns: [] };
  let header: string[];
  try {
    header = await readHeader(file);
  } catch {
    return { ok: false, missingColumns: expected };
  }
  const have = new Set(header);
  const missingColumns = expected.filter((c) => !have.has(c));
  return { ok: missingColumns.length === 0, missingColumns };
}

/** Match uploads to the 8 official names case-insensitively, ignoring any folder path. */
export function canonicalName(rawName: string): string {
  const base = rawName.split(/[\\/]/).pop() ?? rawName;
  const lower = base.toLowerCase();
  for (const name of Object.keys(EXPECTED_COLUMNS)) {
    if (name.toLowerCase() === lower) return name;
  }
  return base;
}
