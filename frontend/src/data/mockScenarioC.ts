// MOCK Scenario C data, hand-edited from the organisers' sample so the demo shows every kind of cost.
// The real solver replaces this. Edits made:
//   1. A072 (contract C012, Priority 1) moved from week 26 to 28  -> C012 finishes 7 days late = 700 points
//   2. A013 (contract C002, Priority 2) last night moved 26 -> 27  -> C002 finishes 7 days late = 70 points
//   3. A046 (contract C007) weeks 11 and 12 become ECLO nights, week 25 dropped -> 2 ECLO nights = 10 points
//   4. A073 moved from week 25 to 26, where the hub tunnel is already full -> extra nights over limit = 7 each

import sample from "./sample.json";
import type { Access, Occupancy } from "../types";

function moveWeek<T extends { activity_id: string; week: string }>(rows: T[], id: string, from: number, to: number): T[] {
  return rows.map((r) => (r.activity_id === id && Number(r.week) === from ? { ...r, week: String(to) } : r));
}

let access: Access[] = sample.access;
let occupancy: Occupancy[] = sample.occupancy;

// 1. Priority 1 contract late
access = moveWeek(access, "A072", 26, 28);
occupancy = moveWeek(occupancy, "A072", 26, 28).map((o) => (o.activity_id === "A072" ? { ...o, co_share_group: "mock" } : o));

// 2. Priority 2 contract late
access = moveWeek(access, "A013", 26, 27);
occupancy = moveWeek(occupancy, "A013", 26, 27).map((o) => (o.activity_id === "A013" && o.week === "27" ? { ...o, co_share_group: "mock" } : o));

// 3. ECLO nights: 1 + 1 + 1.5 + 1.5 = 5 nights of work, so the 5th night is not needed
access = access
  .filter((a) => !(a.activity_id === "A046" && a.week === "25"))
  .map((a) => (a.activity_id === "A046" && (a.week === "11" || a.week === "12") ? { ...a, eclo: "1" } : a));
occupancy = occupancy.filter((o) => !(o.activity_id === "A046" && o.week === "25"));

// 4. Extra nights: squeeze A073 into week 26 where its spots are already at the limit
access = moveWeek(access, "A073", 25, 26);
occupancy = moveWeek(occupancy, "A073", 25, 26).map((o) => (o.activity_id === "A073" ? { ...o, co_share_group: "mock" } : o));

export const mockScenarioC = { access, occupancy };
