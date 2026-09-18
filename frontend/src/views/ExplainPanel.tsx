// The story of one job, in plain English. The reasons come from the backend
// (result.explanations); everything else is a readable re-print of the two
// schedule tables plus RESULTS.csv. Nothing is scored or re-checked here.

import { useMemo } from "react";
import type { SolveResult } from "../types";
import {
  buildIndex,
  cellKey,
  lateLabel,
  locationLabelWithLine,
  num,
  weekRangeLabel,
} from "../lib/grid";
import "./grid.css";

export type ExplainPanelProps = {
  result: SolveResult;
  activityId: string;
  onClose: () => void;
};

export function ExplainPanel({ result, activityId, onClose }: ExplainPanelProps) {
  const idx = useMemo(() => buildIndex(result), [result]);
  const activity = idx.activityById.get(activityId);
  const contract = activity ? idx.contractById.get(activity.contract_number) : undefined;
  const reasons = result.explanations?.[activityId] ?? [];
  const nights = idx.accessByActivity.get(activityId) ?? [];
  const occupancy = useMemo(
    () => idx.occupancyByActivity.get(activityId) ?? [],
    [idx, activityId],
  );
  const horizon = idx.horizonStart;

  // Distinct spots this job books, in the order they first appear.
  const spots = useMemo(() => {
    const seen: string[] = [];
    for (const row of occupancy) if (!seen.includes(row.location_id)) seen.push(row.location_id);
    return seen;
  }, [occupancy]);

  // Who else sits in the same (location, week, co_share_group)? Purely descriptive.
  const sharers = useMemo(() => {
    const byActivity = new Map<string, Set<number>>();
    for (const mine of occupancy) {
      const week = num(mine.week);
      for (const other of idx.occupancyByCell.get(cellKey(mine.location_id, week)) ?? []) {
        if (other.activity_id === activityId) continue;
        if (other.co_share_group !== mine.co_share_group) continue;
        const weeks = byActivity.get(other.activity_id) ?? new Set<number>();
        weeks.add(week);
        byActivity.set(other.activity_id, weeks);
      }
    }
    return [...byActivity.entries()]
      .map(([id, weeks]) => ({ id, weeks: [...weeks].sort((a, b) => a - b) }))
      .sort((a, b) => a.id.localeCompare(b.id));
  }, [occupancy, idx, activityId]);

  const priority = contract?.contract_priority || "3";
  const outcome = lateLabel(contract ? idx.resultByContract.get(contract.contract_number) : undefined);

  return (
    <aside className="explain" aria-label={`Why ${activityId} is scheduled where it is`}>
      <div className="explain-head">
        <div>
          <div className="eyebrow">Job</div>
          <h2>
            {activityId} <span className={"pri p" + priority}>P{priority}</span>
          </h2>
          <p className="grid-hint">
            {contract ? contract.contract_number : "unknown contract"}
            {contract?.contract_description ? ` · ${contract.contract_description}` : ""}
          </p>
        </div>
        <button type="button" className="chip chip-close" onClick={onClose}>
          Close
        </button>
      </div>

      <h3>Why it is where it is</h3>
      {reasons.length > 0 ? (
        <ul className="reasons">
          {reasons.map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>
      ) : (
        <p className="grid-hint">No explanation was returned for this job.</p>
      )}

      {activity && (
        <>
          <h3>The job</h3>
          <dl className="explain-dl">
            <dt>From</dt>
            <dd>{locationLabelWithLine(activity.start_location_id, idx.lineNames)}</dd>
            <dt>To</dt>
            <dd>{locationLabelWithLine(activity.end_location_id, idx.lineNames)}</dd>
            <dt>Work needed</dt>
            <dd>
              {num(activity.total_accesses)} {num(activity.total_accesses) === 1 ? "night" : "nights"}
            </dd>
            <dt>Earliest start</dt>
            <dd>{activity.planned_start_date || "not set"}</dd>
            <dt>Work type</dt>
            <dd>
              {contract?.nature_of_activity ?? "unknown"}
              {contract?.access_type ? ` · access ${contract.access_type}` : ""}
            </dd>
            {activity.predecessor_activity_id ? (
              <>
                <dt>Waits for</dt>
                <dd>{activity.predecessor_activity_id} to finish first</dd>
              </>
            ) : null}
          </dl>
        </>
      )}

      <h3>When it works</h3>
      {nights.length > 0 ? (
        <ul className="plain">
          {nights.map((n) => (
            <li key={`${n.activity_id}-${num(n.week)}`}>
              {weekRangeLabel(horizon, num(n.week))}
              {num(n.eclo) === 1 ? <span className="eclo-tag"> E · longer night</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="grid-hint">No nights were scheduled for this job.</p>
      )}

      <h3>Spots it books</h3>
      {spots.length > 0 ? (
        <ul className="plain">
          {spots.map((s) => (
            <li key={s} title={s}>
              {locationLabelWithLine(s, idx.lineNames)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="grid-hint">No spots were booked for this job.</p>
      )}

      <h3>Shares possessions with</h3>
      {sharers.length > 0 ? (
        <ul className="plain">
          {sharers.map((s) => (
            <li key={s.id}>
              <b>{s.id}</b> · {s.weeks.length === 1 ? "week" : "weeks"} {s.weeks.join(", ")}
            </li>
          ))}
        </ul>
      ) : (
        <p className="grid-hint">Nobody else — it has its possessions to itself.</p>
      )}

      <h3>Contract outcome</h3>
      <p className={outcome.late > 0 ? "outcome-late" : "outcome-ok"}>
        {contract?.contract_number ?? "This contract"} is {outcome.text}
        {contract?.planned_completion_date ? ` against its planned date of ${contract.planned_completion_date}` : ""}.
      </p>
      <p className="grid-hint">
        Spot names read as station–station plus the track direction (EB and WB are separate tracks).
      </p>
    </aside>
  );
}
