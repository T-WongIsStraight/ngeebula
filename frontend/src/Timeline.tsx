// Gantt-style grid: one row per job, one column per week.
// A dot means "this job works one night that week". Click a job to explain it.

import { Fragment, useState } from "react";
import type { SolveResult } from "./types";
import { weekLabel, earliestWeek } from "./schedule";

type Props = {
  result: SolveResult;
  weeks: number[];
  selected: string | null;
  onSelect: (activityId: string) => void;
};

export function Timeline({ result, weeks, selected, onSelect }: Props) {
  // Contracts start folded so 14 rows fit on one screen. Click one to see its jobs.
  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setOpen((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  // Quick lookup: "A001-22" -> eclo flag
  const worked = new Map<string, string>();
  for (const a of result.access) worked.set(`${a.activity_id}-${a.week}`, a.eclo);

  // First and last working week per job, so we can show waits inside a run
  const span = new Map<string, [number, number]>();
  for (const a of result.access) {
    const w = Number(a.week);
    const s = span.get(a.activity_id);
    span.set(a.activity_id, s ? [Math.min(s[0], w), Math.max(s[1], w)] : [w, w]);
  }

  const contracts = [...result.contracts].sort((a, b) => Number(a.contract_priority) - Number(b.contract_priority));
  const lateOf = new Map(result.results.map((r) => [r.contract_number, Number(r.overrun_days)]));

  return (
    <div className="timeline">
      <table>
        <thead>
          <tr>
            <th className="sticky">Contract / job</th>
            {weeks.map((w) => (
              <th key={w} title={`Week ${w} starts ${weekLabel(result.horizonStart, w)}`}>
                {w}<small>{weekLabel(result.horizonStart, w)}</small>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {contracts.map((c) => {
            const jobs = result.activities.filter((a) => a.contract_number === c.contract_number);
            const isOpen = open.has(c.contract_number);
            const late = lateOf.get(c.contract_number) ?? 0;
            const deadlineWeek = earliestWeek(result.horizonStart, c.planned_completion_date);
            const first = Math.min(...jobs.map((a) => span.get(a.activity_id)?.[0] ?? Infinity));
            const last = Math.max(...jobs.map((a) => span.get(a.activity_id)?.[1] ?? -Infinity));
            return (
              <Fragment key={c.contract_number}>
                <tr className="contract-row" onClick={() => toggle(c.contract_number)}>
                  <td className="sticky">
                    <span className="caret">{isOpen ? "-" : "+"}</span>
                    <span className={"pri p" + c.contract_priority}>P{c.contract_priority}</span>
                    <span className="cname">{c.contract_number} <small>{jobs.length} jobs</small></span>
                    {late > 0 ? <span className="late-tag">{late} days late</span> : <span className="ok-tag">on time</span>}
                  </td>
                  {weeks.map((w) => (
                    <td
                      key={w}
                      className={(w >= first && w <= last ? "span" : "") + (w === deadlineWeek ? " deadline" : "")}
                      title={w === deadlineWeek ? `Deadline ${c.planned_completion_date}` : undefined}
                    />
                  ))}
                </tr>
                {isOpen && jobs.map((a) => {
                  const [s0, s1] = span.get(a.activity_id) ?? [0, 0];
                  return (
                    <tr
                      key={a.activity_id}
                      className={"job" + (selected === a.activity_id ? " selected" : "")}
                      onClick={() => onSelect(a.activity_id)}
                    >
                      <td className="sticky" title={`${a.start_location_id} to ${a.end_location_id}`}>
                        <span className="indent" />{a.activity_id} <small>{a.total_accesses} nights</small>
                      </td>
                      {weeks.map((w) => {
                        const eclo = worked.get(`${a.activity_id}-${w}`);
                        const waiting = eclo === undefined && w > s0 && w < s1;
                        return (
                          <td key={w} className={w === deadlineWeek ? "deadline" : ""}>
                            {eclo !== undefined && <span className={"dot p" + c.contract_priority + (eclo === "1" ? " eclo" : "")}>{eclo === "1" ? "E" : ""}</span>}
                            {waiting && <span className="dot wait" title="Waiting: a spot it needs was taken" />}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      <div className="legend">
        <span><i className="dot p1" /> Priority 1</span>
        <span><i className="dot p2" /> Priority 2</span>
        <span><i className="dot p3" /> Priority 3</span>
        <span><i className="dot p3 eclo">E</i> ECLO night</span>
        <span><i className="dot wait" /> waiting for a spot</span>
        <span><i className="dl" /> deadline week</span>
      </div>
      <p className="hint">Each dot is one night of work. Click a contract to open its jobs. Click a job to see why it is there.</p>
    </div>
  );
}
