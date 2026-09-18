// Shapes of everything the backend returns. Mirrors CLAUDE.md §8.2 exactly.
// The frontend never computes feasibility, score or excess: it displays what
// the backend's validator reports.

export type Scenario = "A" | "B" | "C";

/** One row of 07_PROJECT_DETAILS.csv. All values arrive as strings. */
export type Contract = {
  contract_number: string;
  contract_description: string;
  contract_award_date: string;
  activity_type: string;
  nature_of_activity: string; // "Live" | "Non-live (Consist)" | "Non-live (Others)"
  contract_priority: string; // "1" | "2" | "3"
  contract_completion_date: string;
  planned_completion_date: string;
  number_of_workfronts: string;
  access_type: string; // "PM" | "PC" | "C"
  number_of_maximum_access_per_week: string;
};

/** One row of 08_ACTIVITY_DETAILS.csv. */
export type Activity = {
  activity_id: string;
  contract_number: string;
  activity_type: string;
  start_location_id: string;
  end_location_id: string;
  total_accesses: string;
  planned_start_date: string;
  predecessor_activity_id: string;
  activity_priority: string; // "1" | "2" | "3"
};

/** One row of 04_LOCATION_SUPPLY.csv. */
export type Location = {
  location_id: string; // e.g. "SEC:ALP:S02_S03:EB" or "PLAT:ALP:S03:EB"
  location_kind: string; // "tunnel sector" | "platform sector"
  line_code: string;
  bound: string; // "EB" | "WB"
  supply_capacity: string;
};

/** One row of 03_SECTORS.csv. */
export type Sector = {
  sector_id: string;
  line_code: string;
  from_station_id: string;
  to_station_id: string;
  seq: string;
  is_shared: string;
};

/** One row of SCHEDULE_ACCESS.csv (one night of work). Numbers may arrive as numbers or strings. */
export type AccessRow = {
  activity_id: string;
  access_seq: number | string;
  week: number | string;
  eclo: number | string; // 0 | 1
  access_night: number | string;
};

/** One row of SCHEDULE_OCCUPANCY.csv. */
export type OccupancyRow = {
  activity_id: string;
  week: number | string;
  location_id: string;
  co_share_group: string; // "b1", "b2", ...
};

/** One row of RESULTS.csv, joined server-side with two contract columns. */
export type ResultRow = {
  scenario: string;
  contract_number: string;
  simulated_completion_date: string;
  overrun_days: number | string;
  contract_priority: string | null;
  planned_completion_date: string | null;
};

export type Violation = { rule: string; severity: "hard"; detail: string };

/** README 2.7 validator report. */
export type Report = {
  scenario: string;
  feasible: boolean;
  hard_violations: Violation[];
  soft_scores: {
    overrun_days_total: number;
    contracts_overrunning: number;
    earliness_days_total: number;
    excess_access_nights_total: number;
    eclo_nights_total: number;
    priority_overrun: Record<"1" | "2" | "3", number>;
    priority_weighted_score: number;
    objective_score: number;
  };
  detail: {
    capacity_hotspots: { location_id: string; week: number; used: number; supply: number }[];
    nights_scheduled: number;
    eclo_nights: number;
  };
};

export type CapacityUsage = { location_id: string; week: number; used: number; supply: number };

/** `result` inside a finished job. */
export type SolveResult = {
  scenario: Scenario;
  instance: {
    horizon_start: string; // ISO date, week 1 starts here (a Monday)
    horizon_weeks: number;
    contracts: Contract[];
    activities: Activity[];
    locations: Location[];
    sectors: Sector[];
  };
  schedule_access: AccessRow[];
  schedule_occupancy: OccupancyRow[];
  results: ResultRow[];
  report: Report;
  capacity_usage: CapacityUsage[];
  explanations: Record<string, string[]>;
  metrics: { wall_time_seconds: number | null; solver_status: string | null; objective_value: number | null };
  warnings: string[];
};

export type JobStatus = "running" | "done" | "infeasible" | "timeout" | "error";

/** `GET /api/jobs/{id}` body. */
export type Job = {
  job_id: string;
  status: JobStatus;
  message: string;
  solver_status: string | null;
  elapsed_s: number;
  error_code?: string;
  result?: SolveResult;
};

/** Error body for any 4xx/5xx. */
export type ApiError = { error_code: string; message: string };

/** The 8 instance files, in order. Uploads are matched by these names (case-insensitive). */
export const INSTANCE_FILES = [
  "01_LINES.csv",
  "02_STATIONS.csv",
  "03_SECTORS.csv",
  "04_LOCATION_SUPPLY.csv",
  "05_BUFFER_LOCATION.csv",
  "06_PARAMETERS.csv",
  "07_PROJECT_DETAILS.csv",
  "08_ACTIVITY_DETAILS.csv",
] as const;

export const SUBMISSION_FILES = ["SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv"] as const;

/** Penalty weights from README 2.5, for LABELS only (the score itself comes from the backend). */
export const POINTS = { ECLO: 5, EXCESS: 7, LATE: { "1": 100, "2": 10, "3": 1 } as Record<string, number> };
