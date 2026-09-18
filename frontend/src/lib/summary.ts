// A read-only "what is in these files" summary shown before the run: row counts
// and the planning horizon out of 06_PARAMETERS. It never decides anything —
// the backend still parses the same files from scratch.

import { splitCsvLine } from "./csvHeader";
import { weekEnd } from "./dates";

type Row = Record<string, string>;

/** Parse a whole CSV into objects keyed by the (lower-cased) header row. */
function parseCsv(text: string): Row[] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length === 0) return [];
  const header = splitCsvLine(lines[0]).map((h) => h.toLowerCase());
  return lines.slice(1).map((line) => {
    const cells = splitCsvLine(line);
    const row: Row = {};
    header.forEach((h, i) => {
      row[h] = cells[i] ?? "";
    });
    return row;
  });
}

export type InstanceSummary = {
  horizonStart: string;
  horizonEnd: string;
  horizonWeeks: number;
  lines: number;
  stations: number;
  hubs: number;
  sectors: number;
  spots: number;
  contracts: number;
  priority1: number;
  jobs: number;
  nightsNeeded: number;
};

/** Build the summary from the 8 files, keyed by their official names. */
export async function summarise(files: Record<string, File>): Promise<InstanceSummary> {
  const read = async (name: string): Promise<Row[]> => {
    const f = files[name];
    if (!f) return [];
    return parseCsv(await f.text());
  };

  const [lines, stations, sectors, supply, params, contracts, activities] = await Promise.all([
    read("01_LINES.csv"),
    read("02_STATIONS.csv"),
    read("03_SECTORS.csv"),
    read("04_LOCATION_SUPPLY.csv"),
    read("06_PARAMETERS.csv"),
    read("07_PROJECT_DETAILS.csv"),
    read("08_ACTIVITY_DETAILS.csv"),
  ]);

  const param = (key: string): string =>
    params.find((r) => (r.key ?? "").trim().toLowerCase() === key)?.value?.trim() ?? "";

  const horizonStart = param("horizon_start");
  const horizonWeeks = Number(param("horizon_weeks")) || 0;

  return {
    horizonStart,
    horizonEnd: horizonWeeks > 0 ? weekEnd(horizonStart, horizonWeeks) : "",
    horizonWeeks,
    lines: lines.length,
    stations: stations.length,
    hubs: stations.filter((r) => (r.is_interchange ?? "").trim() === "1").length,
    sectors: sectors.length,
    spots: supply.length,
    contracts: contracts.length,
    priority1: contracts.filter((r) => (r.contract_priority ?? "").trim() === "1").length,
    jobs: activities.length,
    nightsNeeded: activities.reduce((sum, r) => sum + (Number(r.total_accesses) || 0), 0),
  };
}
