// FAKE SOLVER for the prototype.
// Later, this file is replaced by a fetch() call to Jeremiah's backend.
// For now it waits 2.5 seconds and returns prototype data:
//   A and B -> the organisers' sample schedule (valid, only Priority 3 lateness)
//   C       -> a hand-edited mock that shows ECLO, extra nights and Priority 1/2 lateness

import sample from "./data/sample.json";
import { mockScenarioC } from "./data/mockScenarioC";
import { POINTS } from "./types";
import type { Scenario, SolveResult, Contract, Activity, Location, Sector, Access, Occupancy, Explanation } from "./types";
import type { Instance } from "./csv";
import { computeResults, latePoints, excessNights, explainActivity } from "./schedule";

// Turn raw tables into the full result the screens need. The backend will do this later.
export function buildResult(
  scenario: Scenario,
  dataNote: string,
  horizonStart: string,
  horizonWeeks: number,
  contracts: Contract[],
  activities: Activity[],
  locations: Location[],
  sectors: Sector[],
  access: Access[],
  occupancy: Occupancy[]
): SolveResult {
  const results = computeResults(scenario, horizonStart, contracts, activities, access);
  const latenessPoints = results.reduce((sum, r) => sum + latePoints(contracts.find((c) => c.contract_number === r.contract_number)!, r), 0);
  const eclo = access.filter((a) => a.eclo === "1").length;
  const excess = excessNights(locations, occupancy);

  const explanations: Record<string, Explanation> = {};
  for (const a of activities) {
    const c = contracts.find((x) => x.contract_number === a.contract_number)!;
    const r = results.find((x) => x.contract_number === a.contract_number)!;
    explanations[a.activity_id] = explainActivity(horizonStart, a, c, r, access, occupancy, locations, activities);
  }

  return {
    scenario, dataNote, horizonStart, horizonWeeks,
    feasible: true, violations: [],
    score: latenessPoints + POINTS.ECLO * eclo + POINTS.EXCESS * excess,
    latenessPoints, ecloNights: eclo, excessNights: excess,
    contracts, activities, locations, sectors, access, occupancy, results, explanations,
  };
}

// Rebuild a result after the schedule tables changed (used when an urgent request is added).
export function rebuildResult(prev: SolveResult, contracts: Contract[], activities: Activity[], access: Access[], occupancy: Occupancy[]): SolveResult {
  return buildResult(prev.scenario, prev.dataNote, prev.horizonStart, prev.horizonWeeks, contracts, activities, prev.locations, prev.sectors, access, occupancy);
}

export async function fakeSolve(scenario: Scenario, instance: Instance): Promise<SolveResult> {
  await new Promise((done) => setTimeout(done, 2500)); // pretend to think

  // The prototype only has a schedule for the sample jobs. If the uploaded files list the same
  // jobs, use the uploaded files; otherwise fall back to the sample instance and say so.
  const ids = new Set(instance.activities.map((a) => a.activity_id));
  const matches = sample.activities.every((a) => ids.has(a.activity_id));
  const inst = matches ? instance : (sample as unknown as Instance);
  const param = (k: string) => inst.params.find((p) => p.key === k)?.value ?? "";
  const useMock = scenario === "C";

  return buildResult(
    scenario,
    (matches ? "" : "The uploaded files list different jobs from the sample, so the sample instance is shown. ") +
      (useMock
        ? "Prototype data: a hand-edited mock so every cost type is visible. Not a real solver result."
        : "Prototype data: the organisers' sample schedule. Not a real solver result."),
    param("horizon_start"),
    Number(param("horizon_weeks")),
    inst.contracts, inst.activities, inst.locations, inst.sectors as unknown as Sector[],
    useMock ? mockScenarioC.access : sample.access,
    useMock ? mockScenarioC.occupancy : sample.occupancy
  );
}
