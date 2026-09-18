// Conflict detection, alternatives, and checking a new urgent request against the schedule.
// Pure functions, no React. The real solver will do this server-side; the logic is the same.

import { POINTS } from "./types";
import type { SolveResult, Activity, Contract, Sector } from "./types";
import { bookingsPerSpotWeek, earliestWeek, spotLabel, weekStart, weekEnd } from "./schedule";

// ---------- shared helpers ----------

type Holder = { activity_id: string; contract_number: string; priority: string };

function holdersAt(result: SolveResult, loc: string, week: number, except?: string): Holder[] {
  const ids = [...new Set(result.occupancy.filter((o) => o.location_id === loc && Number(o.week) === week && o.activity_id !== except).map((o) => o.activity_id))];
  return ids.map((id) => {
    const a = result.activities.find((x) => x.activity_id === id);
    const c = result.contracts.find((x) => x.contract_number === a?.contract_number);
    return { activity_id: id, contract_number: a?.contract_number ?? "?", priority: c?.contract_priority ?? "3" };
  });
}

function weight(priority: string): number {
  return POINTS.LATE[priority] ?? 1;
}

// Every spot a job books: the tunnels from start to end, plus the platform of every station touched.
export function spotsFor(sectors: Sector[], startId: string, endId: string): string[] {
  const [, line, , bound] = startId.split(":");
  const key = (id: string) => id.split(":").slice(0, 3).join(":");
  const onLine = sectors.filter((s) => s.line_code === line).sort((a, b) => Number(a.seq) - Number(b.seq));
  const i0 = onLine.findIndex((s) => s.sector_id === key(startId));
  const i1 = onLine.findIndex((s) => s.sector_id === key(endId));
  if (i0 < 0 || i1 < 0) return [];
  const [a, b] = i0 <= i1 ? [i0, i1] : [i1, i0];
  const run = onLine.slice(a, b + 1);
  const stations = [run[0].from_station_id, ...run.map((s) => s.to_station_id)];
  return [
    ...run.map((s) => `${s.sector_id}:${bound}`),
    ...stations.map((st) => `PLAT:${line}:${st}:${bound}`),
  ];
}

// ---------- 1. conflicts found in the schedule ----------

export type Conflict = {
  activity_id: string;
  contract_number: string;
  priority: string;
  week: number; // the week the job wanted but could not have
  spots: string[]; // which of its spots were full
  holders: Holder[]; // who had them
  resolution: string; // what the planner did about it
  lateDays: number; // how late its contract ended up
};

export function detectConflicts(result: SolveResult): Conflict[] {
  const used = bookingsPerSpotWeek(result.occupancy);
  const limit = new Map(result.locations.map((l) => [l.location_id, Number(l.supply_capacity)]));
  const lateOf = new Map(result.results.map((r) => [r.contract_number, Number(r.overrun_days)]));
  const out: Conflict[] = [];

  for (const a of result.activities) {
    const c = result.contracts.find((x) => x.contract_number === a.contract_number)!;
    const weeks = result.access.filter((x) => x.activity_id === a.activity_id).map((x) => Number(x.week)).sort((p, q) => p - q);
    if (weeks.length === 0) continue;
    const earliest = earliestWeek(result.horizonStart, a.planned_start_date);
    const first = weeks[0], last = weeks[weeks.length - 1];
    const worked = new Set(weeks);
    const mySpots = [...new Set(result.occupancy.filter((o) => o.activity_id === a.activity_id).map((o) => o.location_id))];

    // Weeks it wanted: before it started, and gaps inside its run
    const wanted: number[] = [];
    for (let w = earliest; w < first; w++) wanted.push(w);
    for (let w = first + 1; w < last; w++) if (!worked.has(w)) wanted.push(w);

    for (const w of wanted) {
      const full = mySpots.filter((s) => (used.get(`${s}|${w}`) ?? 0) >= (limit.get(s) ?? 0));
      if (full.length === 0) continue;
      const holders = [...new Map(full.flatMap((s) => holdersAt(result, s, w, a.activity_id)).map((h) => [h.activity_id, h])).values()];
      const next = weeks.find((x) => x > w)!;
      out.push({
        activity_id: a.activity_id,
        contract_number: c.contract_number,
        priority: c.contract_priority,
        week: w,
        spots: full,
        holders,
        resolution: w < first ? `Start moved to week ${next}` : `Paused, resumed week ${next}`,
        lateDays: lateOf.get(c.contract_number) ?? 0,
      });
    }
  }
  // Most important contracts first, then by week
  return out.sort((p, q) => Number(p.priority) - Number(q.priority) || p.week - q.week);
}

// One line per job instead of one per week: "A019 waited weeks 11, 12 for ..."
export type ConflictGroup = Conflict & { weeks: number[] };

export function groupConflicts(conflicts: Conflict[]): ConflictGroup[] {
  const byJob = new Map<string, ConflictGroup>();
  for (const c of conflicts) {
    const g = byJob.get(c.activity_id);
    if (!g) { byJob.set(c.activity_id, { ...c, weeks: [c.week] }); continue; }
    g.weeks.push(c.week);
    for (const s of c.spots) if (!g.spots.includes(s)) g.spots.push(s);
    for (const h of c.holders) if (!g.holders.some((x) => x.activity_id === h.activity_id)) g.holders.push(h);
  }
  // Late contracts first, then most important, then longest wait
  return [...byJob.values()].sort(
    (p, q) => (q.lateDays > 0 ? 1 : 0) - (p.lateDays > 0 ? 1 : 0) || Number(p.priority) - Number(q.priority) || q.weeks.length - p.weeks.length
  );
}

// ---------- 2. alternatives for a conflict ----------

export type Alternative = {
  title: string;
  detail: string;
  cost: number; // points this option adds
  saves: number; // points this option removes
  allowed: boolean; // under the current scenario
};

export function suggestAlternatives(result: SolveResult, conflict: Conflict): Alternative[] {
  const s = result.scenario;
  const myWeight = weight(conflict.priority);
  const out: Alternative[] = [];
  // How many days this would claw back: at most one week per conflict week, capped by actual lateness
  const daysSaved = Math.min(7, conflict.lateDays);

  // a. Swap with a less important holder
  for (const h of conflict.holders) {
    if (Number(h.priority) > Number(conflict.priority)) {
      const hw = weight(h.priority);
      out.push({
        title: `Swap with ${h.activity_id} (${h.contract_number}, Priority ${h.priority})`,
        detail: `Give ${conflict.activity_id} the week ${conflict.week} slot and push ${h.activity_id} back one week. The less important contract absorbs the delay.`,
        cost: hw * 7,
        saves: myWeight * daysSaved,
        allowed: true,
      });
    }
  }
  // b. ECLO: two longer nights do three nights of work, so the job finishes a week earlier
  out.push({
    title: "Use 2 ECLO nights",
    detail: `Two early-closure nights on ${conflict.activity_id} count as 3 nights of work, finishing about a week earlier.`,
    cost: 2 * POINTS.ECLO,
    saves: myWeight * daysSaved,
    allowed: s !== "A",
  });
  // c. Overbook the full spot for that week
  out.push({
    title: `Overbook ${conflict.spots.map(spotLabel).slice(0, 2).join(", ")}${conflict.spots.length > 2 ? " and more" : ""} in week ${conflict.week}`,
    detail: `Squeeze ${conflict.activity_id} in above the weekly limit. Needs an extra access-night to be secured operationally.`,
    cost: conflict.spots.length * POINTS.EXCESS,
    saves: myWeight * daysSaved,
    allowed: s !== "A",
  });
  // d. Accept the delay (what the planner did)
  out.push({
    title: "Keep the planner's choice",
    detail: conflict.resolution + (conflict.lateDays ? `. Contract ends ${conflict.lateDays} days late.` : ". Contract still finishes on time."),
    cost: 0,
    saves: 0,
    allowed: true,
  });
  return out.sort((p, q) => (q.saves - q.cost) - (p.saves - p.cost));
}

// ---------- 3. checking a brand-new urgent request ----------

export type UrgentRequest = {
  title: string;
  startId: string;
  endId: string;
  nights: number;
  earliestWeek: number;
  priority: "1" | "2" | "3";
  nature: "Live" | "Non-live (Consist)" | "Non-live (Others)";
};

export type WeekCheck = {
  week: number;
  clear: boolean;
  blockers: { spot: string; used: number; limit: number; holders: Holder[] }[];
  overbookable: boolean; // every blocker is only 1 over and the scenario allows it
};

export type RequestCheck = {
  spots: string[];
  weeks: WeekCheck[];
  plan: number[]; // the weeks we would give it, one night per week
  finishWeek: number | null;
  conflictsSkipped: number;
  bumpable: { week: number; holders: Holder[] }[]; // weeks where every holder is less important
};

export function checkRequest(result: SolveResult, req: UrgentRequest): RequestCheck {
  const spots = spotsFor(result.sectors, req.startId, req.endId);
  // Live-rail work also closes the opposite rail
  const allSpots = req.nature === "Live" ? [...spots, ...spots.map((s) => s.replace(/:EB$/, ":__").replace(/:WB$/, ":EB").replace(/:__$/, ":WB"))] : spots;
  const used = bookingsPerSpotWeek(result.occupancy);
  const limit = new Map(result.locations.map((l) => [l.location_id, Number(l.supply_capacity)]));
  const allowOver = result.scenario !== "A";

  const weeks: WeekCheck[] = [];
  const plan: number[] = [];
  const bumpable: RequestCheck["bumpable"] = [];
  for (let w = req.earliestWeek; w <= result.horizonWeeks && plan.length < req.nights; w++) {
    const blockers = allSpots
      .map((spot) => ({ spot, used: used.get(`${spot}|${w}`) ?? 0, limit: limit.get(spot) ?? 0, holders: holdersAt(result, spot, w) }))
      .filter((b) => b.used >= b.limit);
    const clear = blockers.length === 0;
    // B allows any overbooking; C allows at most 1 over, so only spots exactly at their limit qualify
    const overbookable = allowOver && (result.scenario === "B" || blockers.every((b) => b.used === b.limit));
    weeks.push({ week: w, clear, blockers, overbookable });
    if (clear) plan.push(w);
    else {
      const holders = [...new Map(blockers.flatMap((b) => b.holders).map((h) => [h.activity_id, h])).values()];
      if (holders.length && holders.every((h) => Number(h.priority) > Number(req.priority))) bumpable.push({ week: w, holders });
    }
  }
  return {
    spots,
    weeks,
    plan,
    finishWeek: plan.length === req.nights ? plan[plan.length - 1] : null,
    conflictsSkipped: weeks.filter((w) => !w.clear).length,
    bumpable,
  };
}

// Put the request into the schedule as a new job and rebuild everything.
export function applyRequest(
  result: SolveResult,
  req: UrgentRequest,
  plan: number[],
  rebuild: (contracts: Contract[], activities: Activity[], access: SolveResult["access"], occupancy: SolveResult["occupancy"]) => SolveResult
): SolveResult {
  const n = result.activities.filter((a) => a.activity_id.startsWith("U")).length + 1;
  const activity_id = `U${String(n).padStart(3, "0")}`;
  const contract_number = `URGENT`;
  const spots = spotsFor(result.sectors, req.startId, req.endId);
  const contracts: Contract[] = result.contracts.some((c) => c.contract_number === contract_number)
    ? result.contracts
    : [...result.contracts, {
        contract_number, contract_description: "Urgent maintenance requests", contract_priority: req.priority,
        planned_completion_date: fmt(weekEnd(result.horizonStart, plan[plan.length - 1])), access_type: "C", nature_of_activity: req.nature,
      }];
  const activity: Activity = {
    activity_id, contract_number, start_location_id: req.startId, end_location_id: req.endId,
    total_accesses: String(req.nights), planned_start_date: fmt(weekStart(result.horizonStart, req.earliestWeek)), activity_priority: "1",
  };
  const access = [...result.access, ...plan.map((w, i) => ({ activity_id, access_seq: String(i + 1), week: String(w), eclo: "0", access_night: "1" }))];
  const occupancy = [...result.occupancy, ...plan.flatMap((w) => spots.map((s) => ({ activity_id, week: String(w), location_id: s, co_share_group: "urgent" })))];
  return rebuild(contracts, [...result.activities, activity], access, occupancy);
}

function fmt(d: Date): string {
  return d.toISOString().slice(0, 10);
}
