// The shapes of the data we work with. One type per CSV file.

export type Scenario = "A" | "B" | "C";

// One row of 07_PROJECT_DETAILS.csv (a contractor)
export type Contract = {
  contract_number: string;
  contract_description: string;
  contract_priority: string; // "1" | "2" | "3"
  planned_completion_date: string;
  access_type: string; // "PM" | "PC" | "C"
  nature_of_activity: string;
};

// One row of 08_ACTIVITY_DETAILS.csv (a job)
export type Activity = {
  activity_id: string;
  contract_number: string;
  start_location_id: string;
  end_location_id: string;
  total_accesses: string;
  planned_start_date: string;
  activity_priority: string;
};

// One row of 04_LOCATION_SUPPLY.csv (a bookable spot and its weekly limit)
export type Location = {
  location_id: string;
  location_kind: string;
  line_code: string;
  bound: string;
  supply_capacity: string;
};

// One row of 03_SECTORS.csv (a tunnel between two stations)
export type Sector = {
  sector_id: string;
  line_code: string;
  from_station_id: string;
  to_station_id: string;
  seq: string;
};

// One row of SCHEDULE_ACCESS.csv (one night of work)
export type Access = {
  activity_id: string;
  access_seq: string;
  week: string;
  eclo: string; // "0" or "1"
  access_night: string;
};

// One row of SCHEDULE_OCCUPANCY.csv (a job occupying a spot in a week)
export type Occupancy = {
  activity_id: string;
  week: string;
  location_id: string;
  co_share_group: string;
};

// One row of RESULTS.csv (when a contract finished)
export type Result = {
  scenario: string;
  contract_number: string;
  simulated_completion_date: string;
  overrun_days: string;
};

// Plain-English story for one job (shown in the Explain panel)
export type Explanation = {
  activity_id: string;
  weeks: number[];
  ecloWeeks: number[];
  nights: string[];
  spots: string[];
  sharers: string[];
  reasons: string[];
};

// Everything the solver gives back to the frontend
export type SolveResult = {
  scenario: Scenario;
  dataNote: string; // where this data came from (prototype only)
  horizonStart: string;
  horizonWeeks: number;
  feasible: boolean;
  violations: string[];
  score: number;
  latenessPoints: number;
  ecloNights: number;
  excessNights: number;
  contracts: Contract[];
  activities: Activity[];
  locations: Location[];
  sectors: Sector[];
  access: Access[];
  occupancy: Occupancy[];
  results: Result[];
  explanations: Record<string, Explanation>;
};

export const POINTS = { ECLO: 5, EXCESS: 7, LATE: { "1": 100, "2": 10, "3": 1 } as Record<string, number> };
