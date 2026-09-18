// The standout feature: type in a new maintenance request, see every clash instantly,
// get the earliest clear slots, and drop it into the schedule with one click.

import { useMemo, useState } from "react";
import type { SolveResult } from "./types";
import { checkRequest, applyRequest, spotsFor } from "./conflicts";
import type { UrgentRequest as Req } from "./conflicts";
import { spotLabel, weekLabel } from "./schedule";
import { rebuildResult } from "./fakeSolver";

type Props = { result: SolveResult; onUpdate: (r: SolveResult) => void; onSelect: (activityId: string) => void };

export function UrgentRequest({ result, onUpdate, onSelect }: Props) {
  const lines = [...new Set(result.sectors.map((s) => s.line_code))];
  const [line, setLine] = useState(lines[0]);
  const [bound, setBound] = useState<"EB" | "WB">("EB");
  const sectorsOnLine = result.sectors.filter((s) => s.line_code === line).sort((a, b) => Number(a.seq) - Number(b.seq));
  const [startSec, setStartSec] = useState(sectorsOnLine[0]?.sector_id ?? "");
  const [endSec, setEndSec] = useState(sectorsOnLine[0]?.sector_id ?? "");
  const [nights, setNights] = useState(2);
  const [earliest, setEarliest] = useState(1);
  const [priority, setPriority] = useState<"1" | "2" | "3">("1");
  const [nature, setNature] = useState<Req["nature"]>("Non-live (Others)");
  const [title, setTitle] = useState("Urgent rail defect repair");
  const [checked, setChecked] = useState<Req | null>(null);
  const [applied, setApplied] = useState<string | null>(null);

  function changeLine(l: string) {
    setLine(l);
    const first = result.sectors.filter((s) => s.line_code === l).sort((a, b) => Number(a.seq) - Number(b.seq))[0]?.sector_id ?? "";
    setStartSec(first); setEndSec(first); setChecked(null);
  }

  const req: Req = { title, startId: `${startSec}:${bound}`, endId: `${endSec}:${bound}`, nights, earliestWeek: earliest, priority, nature };
  const check = useMemo(() => (checked ? checkRequest(result, checked) : null), [checked, result]);
  const spots = spotsFor(result.sectors, req.startId, req.endId);

  function apply() {
    if (!check || !checked || check.plan.length === 0) return;
    const next = applyRequest(result, checked, check.plan, (c, a, acc, occ) => rebuildResult(result, c, a, acc, occ));
    const id = next.activities[next.activities.length - 1].activity_id;
    onUpdate(next);
    setApplied(id);
    setChecked(null);
  }

  return (
    <div className="card urgent">
      <h2>Add an urgent request</h2>
      <p className="lead">A new job just came in. Describe it and the tool checks every week for clashes, names who is in the way, and finds the earliest clear slots.</p>

      <div className="form">
        <label>Request<input value={title} onChange={(e) => { setTitle(e.target.value); setChecked(null); }} /></label>
        <label>Line
          <select value={line} onChange={(e) => changeLine(e.target.value)}>
            {lines.map((l) => <option key={l} value={l}>{l === "ALP" ? "Alpha" : l === "BET" ? "Beta" : l}</option>)}
          </select>
        </label>
        <label>Rail
          <select value={bound} onChange={(e) => { setBound(e.target.value as "EB" | "WB"); setChecked(null); }}>
            <option value="EB">Eastbound</option><option value="WB">Westbound</option>
          </select>
        </label>
        <label>From tunnel
          <select value={startSec} onChange={(e) => { setStartSec(e.target.value); setChecked(null); }}>
            {sectorsOnLine.map((s) => <option key={s.sector_id} value={s.sector_id}>{s.from_station_id}-{s.to_station_id}</option>)}
          </select>
        </label>
        <label>To tunnel
          <select value={endSec} onChange={(e) => { setEndSec(e.target.value); setChecked(null); }}>
            {sectorsOnLine.map((s) => <option key={s.sector_id} value={s.sector_id}>{s.from_station_id}-{s.to_station_id}</option>)}
          </select>
        </label>
        <label>Nights needed<input type="number" min={1} max={10} value={nights} onChange={(e) => { setNights(Number(e.target.value) || 1); setChecked(null); }} /></label>
        <label>Earliest week
          <select value={earliest} onChange={(e) => { setEarliest(Number(e.target.value)); setChecked(null); }}>
            {Array.from({ length: result.horizonWeeks }, (_, i) => i + 1).map((w) => <option key={w} value={w}>Week {w} ({weekLabel(result.horizonStart, w)})</option>)}
          </select>
        </label>
        <label>Priority
          <select value={priority} onChange={(e) => { setPriority(e.target.value as "1" | "2" | "3"); setChecked(null); }}>
            <option value="1">1 · urgent</option><option value="2">2 · normal</option><option value="3">3 · low</option>
          </select>
        </label>
        <label>Work type
          <select value={nature} onChange={(e) => { setNature(e.target.value as Req["nature"]); setChecked(null); }}>
            <option>Non-live (Others)</option><option>Non-live (Consist)</option><option>Live</option>
          </select>
        </label>
      </div>
      <p className="hint">Books {spots.length} spots each night: {spots.map(spotLabel).join(", ") || "choose a section"}{nature === "Live" ? ", plus the opposite rail" : ""}.</p>
      <div className="actions">
        <button className="primary" onClick={() => { setChecked(req); setApplied(null); }} disabled={spots.length === 0}>Check for clashes</button>
        {applied && <span className="applied">Added to the schedule as <button className="link" onClick={() => onSelect(applied)}>{applied}</button>. Score and grids are updated.</span>}
      </div>

      {check && checked && (
        <div className="check">
          <div className={"verdict " + (check.finishWeek ? (check.conflictsSkipped ? "warnbox" : "goodbox") : "badbox")}>
            <div className="verdict-badge">{check.finishWeek ? (check.conflictsSkipped ? "FITS, WITH CLASHES" : "FITS CLEANLY") : "DOES NOT FIT"}</div>
            <p>
              {check.finishWeek
                ? `${checked.nights} night(s) can go in week${check.plan.length > 1 ? "s" : ""} ${check.plan.join(", ")}, finishing week ${check.finishWeek} (${weekLabel(result.horizonStart, check.finishWeek)}). ${check.conflictsSkipped ? `${check.conflictsSkipped} week(s) skipped because a spot was full.` : "No week had to be skipped."}`
                : `Only ${check.plan.length} of ${checked.nights} nights fit before the end of the planning period. Reduce nights, start earlier, or bump a less important job.`}
            </p>
          </div>

          <div className="weekstrip">
            {check.weeks.map((w) => (
              <div key={w.week} className={"wk " + (w.clear ? "clear" : w.overbookable ? "tight" : "full")} title={w.clear ? `Week ${w.week}: clear` : `Week ${w.week}: ${w.blockers.map((b) => `${spotLabel(b.spot)} ${b.used}/${b.limit}`).join(", ")}`}>
                <b>{w.week}</b><span>{w.clear ? "clear" : w.overbookable ? "tight" : "full"}</span>
              </div>
            ))}
          </div>

          {check.weeks.some((w) => !w.clear) && (
            <div className="clashes">
              <h3>Clashes found</h3>
              <ul>
                {check.weeks.filter((w) => !w.clear).map((w) => (
                  <li key={w.week}>
                    <b>Week {w.week}:</b>{" "}
                    {w.blockers.map((b) => (
                      <span key={b.spot} className="blocker">
                        {spotLabel(b.spot)} is {b.used >= b.limit ? "full" : "busy"} ({b.used}/{b.limit}
                        {b.holders.length ? `, ${b.holders.map((h) => `${h.activity_id} P${h.priority}`).join(" + ")}` : ""})
                      </span>
                    ))}
                    {w.overbookable && <em className="hint"> Could overbook here for +7 points per spot.</em>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {check.bumpable.length > 0 && (
            <div className="clashes">
              <h3>Alternative: bump a less important job</h3>
              <ul>
                {check.bumpable.map((b) => (
                  <li key={b.week}>
                    Week {b.week} is held only by lower-priority work: {b.holders.map((h) => (
                      <button key={h.activity_id} className="chip" onClick={() => onSelect(h.activity_id)}>{h.activity_id} <small>P{h.priority}</small></button>
                    ))}. Moving it a week later frees the slot for this Priority {checked.priority} request.
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="actions">
            <button className="primary" onClick={apply} disabled={!check.finishWeek}>Add to schedule in the clear weeks</button>
            <button onClick={() => setChecked(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}
