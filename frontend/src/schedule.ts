// All the schedule maths in one place. Pure functions, no React.
// Later the backend does most of this; the frontend keeps it for display and mock data.

import { POINTS } from "./types";
import type { Access, Activity, Contract, Location, Occupancy, Result, Scenario, Explanation } from "./types";

const DAY = 24 * 60 * 60 * 1000;

function parseDate(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}
function fmt(d: Date): string {
  return d.toISOString().slice(0, 10);
}

// Week N starts on horizon_start + 7*(N-1) days and ends 6 days later (a Sunday).
export function weekStart(horizonStart: string, week: number): Date {
  return new Date(parseDate(horizonStart).getTime() + (week - 1) * 7 * DAY);
}
export function weekEnd(horizonStart: string, week: number): Date {
  return new Date(weekStart(horizonStart, week).getTime() + 6 * DAY);
}
export function weekLabel(horizonStart: string, week: number): string {
  const s = weekStart(horizonStart, week);
  return s.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}
// The first week an activity may start = the week containing its planned_start_date
export function earliestWeek(horizonStart: string, plannedStart: string): number {
  const days = (parseDate(plannedStart).getTime() - parseDate(horizonStart).getTime()) / DAY;
  return Math.max(1, Math.floor(days / 7) + 1);
}

// RESULTS.csv rebuilt from the Gantt: a contract finishes on the Sunday of its last working week.
export function computeResults(
  scenario: Scenario,
  horizonStart: string,
  contracts: Contract[],
  activities: Activity[],
  access: Access[]
): Result[] {
  return contracts.map((c) => {
    const ids = new Set(activities.filter((a) => a.contract_number === c.contract_number).map((a) => a.activity_id));
    const lastWeek = Math.max(0, ...access.filter((a) => ids.has(a.activity_id)).map((a) => Number(a.week)));
    const finish = weekEnd(horizonStart, lastWeek);
    const late = Math.max(0, Math.round((finish.getTime() - parseDate(c.planned_completion_date).getTime()) / DAY));
    return { scenario, contract_number: c.contract_number, simulated_completion_date: fmt(finish), overrun_days: String(late) };
  });
}

// Points for one contract being late = priority weight x late days
export function latePoints(contract: Contract, result: Result): number {
  return POINTS.LATE[contract.contract_priority] * Number(result.overrun_days);
}

// How full is each spot each week? "SEC:...:EB|22" -> number of bookings.
// A booking = one distinct co_share_group at that spot that week.
export function bookingsPerSpotWeek(occupancy: Occupancy[]): Map<string, number> {
  const groups = new Map<string, Set<string>>();
  for (const o of occupancy) {
    const key = `${o.location_id}|${o.week}`;
    if (!groups.has(key)) groups.set(key, new Set());
    groups.get(key)!.add(o.co_share_group);
  }
  return new Map([...groups].map(([k, v]) => [k, v.size]));
}

// Bookings over each spot's weekly limit, summed
export function excessNights(locations: Location[], occupancy: Occupancy[]): number {
  const limit = new Map(locations.map((l) => [l.location_id, Number(l.supply_capacity)]));
  let total = 0;
  for (const [key, used] of bookingsPerSpotWeek(occupancy)) {
    total += Math.max(0, used - (limit.get(key.split("|")[0]) ?? 0));
  }
  return total;
}

// Short label for a spot: "SEC:ALP:S01_S02:EB" -> "S01-S02 EB", "PLAT:ALP:H01:WB" -> "H01 platform WB"
export function spotLabel(id: string): string {
  const [kind, , name, bound] = id.split(":");
  return kind === "PLAT" ? `${name} platform ${bound}` : `${name.replace("_", "-")} ${bound}`;
}

// A plain-English story for one job, worked out from the schedule itself.
// The real solver will send better reasons; this is what we can say from the data alone.
export function explainActivity(
  horizonStart: string,
  activity: Activity,
  contract: Contract,
  result: Result,
  access: Access[],
  occupancy: Occupancy[],
  locations: Location[],
  activities: Activity[]
): Explanation {
  const mine = access.filter((a) => a.activity_id === activity.activity_id).sort((a, b) => Number(a.week) - Number(b.week));
  const weeks = mine.map((a) => Number(a.week));
  const first = weeks[0], last = weeks[weeks.length - 1];
  const earliest = earliestWeek(horizonStart, activity.planned_start_date);
  const eclo = mine.filter((a) => a.eclo === "1").length;
  const spots = [...new Set(occupancy.filter((o) => o.activity_id === activity.activity_id).map((o) => o.location_id))];
  const limit = new Map(locations.map((l) => [l.location_id, Number(l.supply_capacity)]));
  const used = bookingsPerSpotWeek(occupancy);

  // Who shares a possession with this job (same spot, week, group)?
  const myKeys = new Set(occupancy.filter((o) => o.activity_id === activity.activity_id).map((o) => `${o.location_id}|${o.week}|${o.co_share_group}`));
  const sharers = [...new Set(
    occupancy.filter((o) => o.activity_id !== activity.activity_id && myKeys.has(`${o.location_id}|${o.week}|${o.co_share_group}`)).map((o) => o.activity_id)
  )].map((id) => {
    const c = activities.find((a) => a.activity_id === id)?.contract_number ?? "?";
    return `${id} (${c})`;
  });

  const reasons: string[] = [];
  if (first > earliest) {
    // Which of its spots were full in the weeks it had to wait?
    const full = new Set<string>();
    for (let w = earliest; w < first; w++) {
      for (const s of spots) if ((used.get(`${s}|${w}`) ?? 0) >= (limit.get(s) ?? 0)) full.add(spotLabel(s));
    }
    reasons.push(
      `Could have started week ${earliest} but started week ${first}` +
        (full.size ? `: ${[...full].slice(0, 3).join(", ")} ${full.size > 3 ? "and more " : ""}were already full.` : ".")
    );
  } else {
    reasons.push(`Started in week ${first}, the earliest week its planned start date allows.`);
  }
  if (last - first + 1 > mine.length) reasons.push(`Skipped ${last - first + 1 - mine.length} week(s) in between, likely because a spot was taken.`);
  if (eclo) reasons.push(`Used ${eclo} ECLO night(s) to finish faster (each counts as 1.5 nights, costs ${POINTS.ECLO} points).`);
  if (sharers.length) reasons.push(`Shares the possession with ${sharers.join(", ")}, which saves capacity.`);
  const late = Number(result.overrun_days);
  reasons.push(
    late > 0
      ? `Contract ${contract.contract_number} (Priority ${contract.contract_priority}) finishes ${result.simulated_completion_date}, ${late} days after its deadline ${contract.planned_completion_date}: +${latePoints(contract, result)} points.`
      : `Contract ${contract.contract_number} (Priority ${contract.contract_priority}) finishes ${result.simulated_completion_date}, on time for its deadline ${contract.planned_completion_date}.`
  );

  return {
    activity_id: activity.activity_id,
    weeks,
    ecloWeeks: mine.filter((a) => a.eclo === "1").map((a) => Number(a.week)),
    nights: mine.map((a) => `wk ${a.week}: night ${a.access_night}${a.eclo === "1" ? " (ECLO)" : ""}`),
    spots: spots.map(spotLabel),
    sharers,
    reasons,
  };
}
