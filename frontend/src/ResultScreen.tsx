// STEP 3: the schedule. Was it valid, what did it score, who is late, and the two grids.

import { useState } from "react";
import type { SolveResult } from "./types";
import { POINTS } from "./types";
import { latePoints } from "./schedule";
import { Timeline } from "./Timeline";
import { Heatmap } from "./Heatmap";
import { ExplainPanel } from "./ExplainPanel";
import { ConflictsCard } from "./ConflictsCard";
import { UrgentRequest } from "./UrgentRequest";
import { detectConflicts, groupConflicts } from "./conflicts";

// CSV text for download, built from the result tables in memory.
function toCsv<T extends object>(rows: T[]): string {
  if (rows.length === 0) return "";
  const keys = Object.keys(rows[0]) as (keyof T)[];
  return [keys.join(","), ...rows.map((r) => keys.map((k) => String(r[k])).join(","))].join("\n");
}
function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

type Props = { result: SolveResult; onUpdate: (r: SolveResult) => void; onBack: () => void; onRestart: () => void };

export function ResultScreen({ result, onUpdate, onBack, onRestart }: Props) {
  const conflictCount = groupConflicts(detectConflicts(result)).length;
  const [tab, setTab] = useState<"gantt" | "heat">("gantt");
  const [selected, setSelected] = useState<string | null>(null);
  const [from, setFrom] = useState(1);
  const [to, setTo] = useState(result.horizonWeeks);

  const allWeeks = Array.from({ length: result.horizonWeeks }, (_, i) => i + 1);
  const weeks = allWeeks.filter((w) => w >= from && w <= to);
  const preset = (a: number, b: number) => { setFrom(a); setTo(b); };

  const lateRows = result.results.filter((r) => Number(r.overrun_days) > 0);

  // Join RESULTS with PROJECT_DETAILS so each row has a priority and points, then sort by priority then lateness.
  const rows = result.results
    .map((r) => {
      const c = result.contracts.find((x) => x.contract_number === r.contract_number)!;
      return { ...r, priority: c.contract_priority, description: c.contract_description, deadline: c.planned_completion_date, points: latePoints(c, r) };
    })
    .sort((a, b) => Number(a.priority) - Number(b.priority) || Number(b.overrun_days) - Number(a.overrun_days));

  // One-sentence verdict for the top of the page
  const worst = rows.find((r) => Number(r.overrun_days) > 0);
  const verdict = !result.feasible
    ? "This schedule breaks a safety rule and cannot be used."
    : lateRows.length === 0
    ? "Every contract finishes on time and no safety rule is broken."
    : `${lateRows.length} of ${result.results.length} contracts finish late. The most important late one is ${worst!.contract_number} (Priority ${worst!.priority}), ${worst!.overrun_days} days late.`;

  return (
    <div className={"result" + (selected ? " with-panel" : "")}>
      <div className="result-main">
        <div className={"verdict " + (result.feasible ? (lateRows.length ? "warnbox" : "goodbox") : "badbox")}>
          <div className="verdict-badge">{result.feasible ? "VALID SCHEDULE" : "RULES BROKEN"}</div>
          <p>{verdict}</p>
        </div>
        {result.dataNote && <p className="hint note">{result.dataNote}</p>}

        <div className="tiles">
          <div className="tile"><b>Rules used</b><span>{result.scenario}</span></div>
          <div className="tile"><b>Score</b><span>{result.score}</span><small>lower is better</small></div>
          <div className="tile"><b>Contracts late</b><span>{lateRows.length} / {result.results.length}</span></div>
          <div className="tile"><b>Conflicts resolved</b><span>{conflictCount}</span><small>clashes the planner settled</small></div>
          <div className="tile"><b>ECLO nights</b><span>{result.ecloNights}</span><small>early closures used</small></div>
          <div className="tile"><b>Extra nights</b><span>{result.excessNights}</span><small>over spot limits</small></div>
        </div>

        {!result.feasible && (
          <div className="card violations">
            <h2>Rules broken</h2>
            <ul>{result.violations.map((v, i) => <li key={i}>{v}</li>)}</ul>
          </div>
        )}

        <div className="row">
          <div className="card grow">
            <h2>Where the score comes from</h2>
            <table className="plain-table">
              <tbody>
                <tr><td>Late contracts <small>priority weight x late days</small></td><td className="num">{result.latenessPoints}</td></tr>
                <tr><td>ECLO nights <small>{result.ecloNights} x {POINTS.ECLO}</small></td><td className="num">{result.ecloNights * POINTS.ECLO}</td></tr>
                <tr><td>Extra nights over spot limits <small>{result.excessNights} x {POINTS.EXCESS}</small></td><td className="num">{result.excessNights * POINTS.EXCESS}</td></tr>
                <tr className="total"><td>Total score</td><td className="num">{result.score}</td></tr>
              </tbody>
            </table>
          </div>
          <div className="card">
            <h2>Download the schedule</h2>
            <p className="hint">The 3 files the official validator reads.</p>
            <div className="downloads">
              <button onClick={() => download("SCHEDULE_ACCESS.csv", toCsv(result.access))}>SCHEDULE_ACCESS.csv <small>when each job works</small></button>
              <button onClick={() => download("SCHEDULE_OCCUPANCY.csv", toCsv(result.occupancy))}>SCHEDULE_OCCUPANCY.csv <small>where it works</small></button>
              <button onClick={() => download("RESULTS.csv", toCsv(result.results))}>RESULTS.csv <small>when each contract finishes</small></button>
            </div>
          </div>
        </div>

        <UrgentRequest result={result} onUpdate={onUpdate} onSelect={setSelected} />

        <ConflictsCard result={result} onSelect={setSelected} />

        <div className="card">
          <h2>Contracts, most important first</h2>
          <div className="scroll-x">
            <table>
              <thead>
                <tr><th>Contract</th><th>Description</th><th>Priority</th><th>Deadline</th><th>Finishes</th><th>Late by</th><th className="num">Points</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.contract_number} className={Number(r.overrun_days) > 0 ? "late" : ""}>
                    <td>{r.contract_number}</td>
                    <td>{r.description}</td>
                    <td><span className={"pri p" + r.priority}>P{r.priority}</span></td>
                    <td>{r.deadline}</td>
                    <td>{r.simulated_completion_date}</td>
                    <td>{Number(r.overrun_days) > 0 ? <b className="warn">{r.overrun_days} days</b> : "on time"}</td>
                    <td className="num">{r.points > 0 ? `+${r.points}` : "0"}</td>
                  </tr>
                ))}
                <tr className="total"><td colSpan={6}>Lateness total</td><td className="num">{result.latenessPoints}</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="toolbar">
            <div className="tabs">
              <button className={tab === "gantt" ? "active" : ""} onClick={() => setTab("gantt")}>Jobs by week</button>
              <button className={tab === "heat" ? "active" : ""} onClick={() => setTab("heat")}>Track spots by week</button>
            </div>
            <div className="range">
              <span className="hint">Weeks</span>
              <select value={from} onChange={(e) => { const v = Number(e.target.value); setFrom(v); if (v > to) setTo(v); }}>
                {allWeeks.map((w) => <option key={w} value={w}>{w}</option>)}
              </select>
              <span className="hint">to</span>
              <select value={to} onChange={(e) => { const v = Number(e.target.value); setTo(v); if (v < from) setFrom(v); }}>
                {allWeeks.map((w) => <option key={w} value={w}>{w}</option>)}
              </select>
              <button onClick={() => preset(1, result.horizonWeeks)}>All</button>
              <button onClick={() => preset(1, 10)}>1-10</button>
              <button onClick={() => preset(11, 20)}>11-20</button>
              <button onClick={() => preset(21, result.horizonWeeks)}>21-{result.horizonWeeks}</button>
            </div>
          </div>
          {tab === "gantt"
            ? <Timeline result={result} weeks={weeks} selected={selected} onSelect={setSelected} />
            : <Heatmap result={result} weeks={weeks} onSelect={setSelected} />}
        </div>

        <div className="stepnav">
          <button onClick={onBack}>Back: change rules</button>
          <button onClick={onRestart}>Start over with new files</button>
        </div>
      </div>

      {selected && <ExplainPanel result={result} activityId={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
