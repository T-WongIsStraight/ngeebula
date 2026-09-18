// Side panel: the plain-English story of one job. Opens when you click a job anywhere.

import type { SolveResult } from "./types";
import { spotLabel } from "./schedule";

type Props = { result: SolveResult; activityId: string; onClose: () => void };

export function ExplainPanel({ result, activityId, onClose }: Props) {
  const a = result.activities.find((x) => x.activity_id === activityId)!;
  const c = result.contracts.find((x) => x.contract_number === a.contract_number)!;
  const e = result.explanations[activityId];

  return (
    <aside className="explain">
      <div className="explain-head">
        <div>
          <div className="eyebrow">Job</div>
          <h2>{a.activity_id} <span className={"pri p" + c.contract_priority}>P{c.contract_priority}</span></h2>
          <div className="hint">{c.contract_number} · {c.contract_description}</div>
        </div>
        <button onClick={onClose} aria-label="Close">Close</button>
      </div>

      <h3>Why it is where it is</h3>
      <ul className="reasons">
        {e.reasons.map((r, i) => <li key={i}>{r}</li>)}
      </ul>

      <h3>The job</h3>
      <dl>
        <dt>Track section</dt><dd>{spotLabel(a.start_location_id)} to {spotLabel(a.end_location_id)}</dd>
        <dt>Work needed</dt><dd>{a.total_accesses} night(s)</dd>
        <dt>Earliest start</dt><dd>{a.planned_start_date}</dd>
        <dt>Work type</dt><dd>{c.nature_of_activity} · access {c.access_type}</dd>
      </dl>

      <h3>When it works</h3>
      <ul className="plain">
        {e.nights.map((n) => <li key={n}>{n}</li>)}
      </ul>

      <h3>Spots it books each night</h3>
      <ul className="plain">
        {e.spots.map((s) => <li key={s}>{s}</li>)}
      </ul>

      {e.sharers.length > 0 && (
        <>
          <h3>Shares the possession with</h3>
          <ul className="plain">{e.sharers.map((s) => <li key={s}>{s}</li>)}</ul>
        </>
      )}
    </aside>
  );
}
