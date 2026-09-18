# Track Access Scheduler — frontend prototype

A clickable demo of the PS1 web app. React + Vite + TypeScript, no backend needed yet. Dark theme, works on phone, tablet and desktop. Written for a works controller at 2 AM.

## Run it

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173

## The 3 steps

A train-line progress bar at the top shows where you are.

**Step 1 · Load files.** Choose the 8 CSV files, or press "Use the sample files instead". Each file is parsed in the browser and checked for the columns it must have. Once all 8 pass, a summary appears: planning period, network size, contracts, jobs, work-nights needed, access-nights available.

**Step 2 · Choose rules.** Pick rulebook A, B or C. Each card shows whether finishing late, ECLO nights and extra nights are allowed and what they cost. A short "Why A/B/C?" box gives when to use it, an example, and the late-day prices.

**Conflicts and alternatives (Step 3).** "Conflicts the planner resolved" lists every job that wanted a spot that was full: which weeks it waited, which spots, who held them, what the planner did, and how late the contract ended up. Open a line for priced alternatives: swap with a lower-priority holder, use 2 ECLO nights, overbook, or keep the planner's choice. Options the rulebook forbids are greyed out.

**Urgent request (Step 3, the standout feature).** Type in a new job: line, rail, from/to tunnel, nights, earliest week, priority, work type. "Check for clashes" scans every week, shows a clear / tight / full strip, names the jobs in the way, suggests bumping lower-priority holders, and proposes the earliest clear weeks. "Add to schedule" drops it in as job U001 under contract URGENT and recalculates score, table, grids and explanations on the spot.

**Light / dark.** A switch in the top-right corner. The knob is a train that slides between Night and Day; colours fade over half a second. The choice is remembered in the browser.

**Step 3 · Schedule.** A loading train runs while the solver works, then:
- A one-sentence verdict: valid or not, how many contracts are late, and the most important late one.
- Tiles: rules used, score, contracts late, ECLO nights, extra nights.
- Where the score comes from (three lines that add up to the score).
- Download buttons for the 3 submission CSVs.
- Contracts table, most important first, with deadline, finish date, late days, points.
- **Jobs by week**: contracts folded by default; open one to see its jobs as dots, one per night. E = ECLO night, hollow dot = waiting for a spot, orange line = deadline week.
- **Track spots by week**: 76 spots, cell = bookings that week, red = over the limit. Click a cell to see who is in it.
- Week range: 1-10, 11-20, 21-30, or any from/to.
- Explain panel: click a job for plain-English reasons, spots booked, sharers, and cost. On phones it slides up from the bottom.

## Prototype data

| Rules picked | Data shown |
| --- | --- |
| A, B | Organisers' sample schedule. Valid. Only Priority 3 contracts late. Score 28. |
| C | Hand-edited mock (`src/data/mockScenarioC.ts`) so every cost type is visible: a P1 contract late (+700), a P2 late (+70), 2 ECLO nights (+10), 5 extra nights (+35). Score 843. |

Uploading real files works for Step 1. For Step 3 the prototype only has a schedule for the sample jobs, so if the uploaded files list different jobs it shows the sample and says so.

## Files (read in this order)

| File | What it does |
| --- | --- |
| `src/App.tsx` | The 3-step flow and the loading overlay |
| `src/StepTrain.tsx` | The train-line progress bar |
| `src/Step1Upload.tsx` | Load and check the 8 files, show the summary |
| `src/Step2Rules.tsx` | Pick A/B/C with the "Why?" box |
| `src/ResultScreen.tsx` | Step 3: verdict, tiles, score, table, grids, explain panel |
| `src/Timeline.tsx` | Jobs-by-week grid |
| `src/Heatmap.tsx` | Spots-by-week grid |
| `src/ExplainPanel.tsx` | Side panel for one job |
| `src/Loading.tsx` | The looping train |
| `src/ConflictsCard.tsx` | The list of resolved conflicts with alternatives |
| `src/UrgentRequest.tsx` | The urgent request form, clash check, and add-to-schedule |
| `src/conflicts.ts` | Conflict detection, alternatives, request checking, applying a request |
| `src/csv.ts` | CSV parsing, file checks, instance summary |
| `src/schedule.ts` | All the maths: week dates, finish dates, late days, points, bookings, explanations |
| `src/fakeSolver.ts` | Pretends to be the solver. **Replace with `fetch("/api/solve")` when the backend is ready.** |
| `src/types.ts` | One TypeScript type per CSV, plus the point values |
| `src/index.css` | All styling, including phone and tablet rules |

## Swapping in the real backend

`fakeSolve(scenario, instance)` returns a `SolveResult` (see `src/types.ts`). The backend should return the same shape: the parsed input tables, the 3 output tables, `feasible`, `violations`, and ideally `explanations` per job. If it only returns the 3 CSVs, call `buildResult(...)` from `fakeSolver.ts` to fill in the rest on the frontend.
