// STEP 3: the schedule. Was it legal, what did it score, who is late, and the
// two grids. Every number on this screen comes from the backend's own report;
// nothing is recomputed here.

import { useMemo, useState } from "react";
import type { SolveResult } from "../types";
import { POINTS, SUBMISSION_FILES } from "../types";
import { downloadUrl } from "../api";
import { formatDate } from "../lib/dates";
import { Timeline } from "../views/Timeline";
import { Heatmap } from "../views/Heatmap";
import { ExplainPanel } from "../views/ExplainPanel";

const FILE_BLURB: Record<string, string> = {
  "SCHEDULE_ACCESS.csv": "when each job works",
  "SCHEDULE_OCCUPANCY.csv": "where it works",
  "RESULTS.csv": "when each contract finishes",
};

/** 25.2 -> "25.2", 30 -> "30". Display only. */
function num(value: number | string | null | undefined): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

type Props = {
  result: SolveResult;
  jobId: string;
  onBack: () => void;
  onRestart: () => void;
};

export function ResultScreen({ result, jobId, onBack, onRestart }: Props) {
  const [tab, setTab] = useState<"gantt" | "heat">("gantt");
  const [selected, setSelected] = useState<string | null>(null);
  const horizonWeeks = result.instance.horizon_weeks;
  const [from, setFrom] = useState(1);
  const [to, setTo] = useState(horizonWeeks);

  const allWeeks = useMemo(() => Array.from({ length: horizonWeeks }, (_, i) => i + 1), [horizonWeeks]);
  const weeks = allWeeks.filter((w) => w >= from && w <= to);
  const preset = (a: number, b: number) => {
    setFrom(a);
    setTo(b);
  };

  const scores = result.report.soft_scores;

  // RESULTS.csv joined with the contract rows, most important first, then latest.
  const rows = useMemo(() => {
    const byNumber = new Map(result.instance.contracts.map((c) => [c.contract_number, c]));
    return result.results
      .map((r) => {
        const c = byNumber.get(r.contract_number);
        return {
          ...r,
          priority: r.contract_priority ?? c?.contract_priority ?? "3",
          description: c?.contract_description ?? "",
          deadline: r.planned_completion_date ?? c?.planned_completion_date ?? "",
          late: Number(r.overrun_days) || 0,
        };
      })
      .sort((a, b) => Number(a.priority) - Number(b.priority) || b.late - a.late);
  }, [result]);

  const lateRows = rows.filter((r) => r.late > 0);
  const worst = lateRows[0];
  const feasible = result.report.feasible;

  const verdict = !feasible
    ? `This schedule breaks ${result.report.hard_violations.length} hard rule${
        result.report.hard_violations.length === 1 ? "" : "s"
      } and cannot be submitted as it stands.`
    : lateRows.length === 0
      ? "Every contract finishes on or before its deadline and no safety rule is broken."
      : `${lateRows.length} of ${rows.length} contracts finish late. The most important late one is ${worst.contract_number} (Priority ${worst.priority}), ${worst.late} days late.`;

  return (
    <div className={"result" + (selected ? " with-panel" : "")}>
      <div className="result-main">
        <div className={"verdict " + (feasible ? (lateRows.length ? "warnbox" : "goodbox") : "badbox")}>
          <div className="verdict-badge">{feasible ? "VALID SCHEDULE" : "RULES BROKEN"}</div>
          <p>{verdict}</p>
        </div>

        <div className="tiles">
          <div className="tile">
            <b>Rules used</b>
            <span>Scenario {result.scenario}</span>
          </div>
          <div className="tile">
            <b>Score</b>
            <span>{num(scores.objective_score)}</span>
            <small>lower is better, 0 is perfect</small>
          </div>
          <div className="tile">
            <b>Contracts late</b>
            <span>
              {scores.contracts_overrunning} / {rows.length}
            </span>
            <small>{scores.overrun_days_total} late days in total</small>
          </div>
          <div className="tile">
            <b>Longer nights</b>
            <span>{scores.eclo_nights_total}</span>
            <small>ECLO nights used</small>
          </div>
          <div className="tile">
            <b>Extra nights</b>
            <span>{scores.excess_access_nights_total}</span>
            <small>over a spot's weekly limit</small>
          </div>
          <div className="tile">
            <b>Scheduler</b>
            <span>{result.metrics.solver_status ?? "—"}</span>
            <small>
              {result.metrics.wall_time_seconds === null ? "run time not reported" : `${num(result.metrics.wall_time_seconds)}s of thinking`}
            </small>
          </div>
        </div>

        {!feasible && (
          <div className="card violations">
            <h2>Rules broken</h2>
            <p className="lead">Reported by the checker on the server. Each line names the rule and what it found.</p>
            <ul className="violation-list">
              {result.report.hard_violations.map((v, i) => (
                <li key={`${v.rule}-${i}`}>
                  <span className="rule-tag">{v.rule}</span>
                  <span>{v.detail}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {result.warnings.length > 0 && (
          <div className="card warnings">
            <h2>Worth knowing</h2>
            <ul className="why-list plain-list">
              {result.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="row">
          <div className="card grow">
            <h2>Where the score comes from</h2>
            <table className="plain-table">
              <tbody>
                <tr>
                  <td>
                    Late contracts <small>priority weight × late days, plus the activity nudge</small>
                  </td>
                  <td className="num">{num(scores.priority_weighted_score)}</td>
                </tr>
                <tr>
                  <td>
                    Longer nights (ECLO){" "}
                    <small>
                      {scores.eclo_nights_total} × {POINTS.ECLO}
                    </small>
                  </td>
                  <td className="num">{num(scores.eclo_nights_total * POINTS.ECLO)}</td>
                </tr>
                <tr>
                  <td>
                    Extra nights over a spot's limit{" "}
                    <small>
                      {scores.excess_access_nights_total} × {POINTS.EXCESS}
                    </small>
                  </td>
                  <td className="num">{num(scores.excess_access_nights_total * POINTS.EXCESS)}</td>
                </tr>
                <tr className="total">
                  <td>Total score for Scenario {result.scenario}</td>
                  <td className="num">{num(scores.objective_score)}</td>
                </tr>
              </tbody>
            </table>
            <p className="hint">
              The total is the score the server calculated for these rules. Anything a scenario forbids outright cannot
              appear here at all.
            </p>
          </div>

          <div className="card">
            <h2>Download the schedule</h2>
            <p className="hint">The 3 files the official validator reads.</p>
            <div className="downloads">
              {SUBMISSION_FILES.map((name) => (
                <a key={name} className="button" href={downloadUrl(jobId, name)} download={name}>
                  {name}
                  <small>{FILE_BLURB[name]}</small>
                </a>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <h2>Contracts, most important first</h2>
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>Contract</th>
                  <th>Description</th>
                  <th>Priority</th>
                  <th>Deadline</th>
                  <th>Finishes</th>
                  <th>Late by</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.contract_number} className={r.late > 0 ? "late" : ""}>
                    <td>{r.contract_number}</td>
                    <td>{r.description}</td>
                    <td>
                      <span className={"pri p" + r.priority}>P{r.priority}</span>
                    </td>
                    <td>{formatDate(r.deadline)}</td>
                    <td>{formatDate(r.simulated_completion_date)}</td>
                    <td>{r.late > 0 ? <b className="warn-text">{r.late} days</b> : "on time"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="toolbar">
            <div className="tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={tab === "gantt"}
                className={tab === "gantt" ? "active" : ""}
                onClick={() => setTab("gantt")}
              >
                Jobs by week
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "heat"}
                className={tab === "heat" ? "active" : ""}
                onClick={() => setTab("heat")}
              >
                Track spots by week
              </button>
            </div>
            <div className="range">
              <span className="hint">Weeks</span>
              <select
                aria-label="First week shown"
                value={from}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setFrom(v);
                  if (v > to) setTo(v);
                }}
              >
                {allWeeks.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
              <span className="hint">to</span>
              <select
                aria-label="Last week shown"
                value={to}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setTo(v);
                  if (v < from) setFrom(v);
                }}
              >
                {allWeeks.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
              <button type="button" onClick={() => preset(1, horizonWeeks)}>
                All
              </button>
              <button type="button" onClick={() => preset(1, Math.min(10, horizonWeeks))}>
                1–10
              </button>
              <button type="button" onClick={() => preset(Math.min(11, horizonWeeks), Math.min(20, horizonWeeks))}>
                11–20
              </button>
              <button type="button" onClick={() => preset(Math.min(21, horizonWeeks), horizonWeeks)}>
                21–{horizonWeeks}
              </button>
            </div>
          </div>
          {tab === "gantt" ? (
            <Timeline result={result} weeks={weeks} selected={selected} onSelect={setSelected} />
          ) : (
            <Heatmap result={result} weeks={weeks} onSelect={setSelected} />
          )}
        </div>

        <div className="stepnav">
          <button type="button" onClick={onBack}>
            Back: change rules
          </button>
          <button type="button" onClick={onRestart}>
            Start over with new files
          </button>
        </div>
      </div>

      {selected && <ExplainPanel result={result} activityId={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
