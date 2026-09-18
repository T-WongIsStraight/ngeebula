// Every clash the planner had to resolve, with who was in the way and the alternatives.

import { useMemo, useState } from "react";
import type { SolveResult } from "./types";
import { detectConflicts, groupConflicts, suggestAlternatives } from "./conflicts";
import { spotLabel } from "./schedule";

type Props = { result: SolveResult; onSelect: (activityId: string) => void };

export function ConflictsCard({ result, onSelect }: Props) {
  const conflicts = useMemo(() => groupConflicts(detectConflicts(result)), [result]);
  const [open, setOpen] = useState<number | null>(null);
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? conflicts : conflicts.slice(0, 8);

  return (
    <div className="card">
      <h2>Conflicts the planner resolved <span className="count">{conflicts.length} jobs</span></h2>
      <p className="lead">Each line is a job that wanted a spot that was already full. The planner made it wait. Open a line to see the alternatives and what each would cost.</p>
      {conflicts.length === 0 && <p>No conflicts. Every job got its spots in the weeks it wanted.</p>}
      <div className="conflicts">
        {shown.map((c, i) => {
          const isOpen = open === i;
          return (
            <div key={`${c.activity_id}-${c.week}`} className={"conflict" + (isOpen ? " open" : "") + " pri-border-p" + c.priority}>
              <button className="conflict-head" onClick={() => setOpen(isOpen ? null : i)}>
                <span className={"pri p" + c.priority}>P{c.priority}</span>
                <span className="conflict-who"><b>{c.activity_id}</b> <small>{c.contract_number}</small></span>
                <span className="conflict-what">
                  waited week{c.weeks.length > 1 ? "s" : ""} {c.weeks.join(", ")} for <b>{c.spots.map(spotLabel).slice(0, 2).join(", ")}{c.spots.length > 2 ? ` +${c.spots.length - 2}` : ""}</b>, held by{" "}
                  {c.holders.map((h) => `${h.activity_id} (P${h.priority})`).join(", ") || "another possession"}
                </span>
                <span className="conflict-res">{c.resolution}{c.lateDays ? <em> · {c.lateDays} days late</em> : ""}</span>
                <span className="caret">{isOpen ? "-" : "+"}</span>
              </button>
              {isOpen && (
                <div className="alts">
                  {suggestAlternatives(result, c).map((a) => (
                    <div key={a.title} className={"alt" + (a.allowed ? "" : " off")}>
                      <div className="alt-head">
                        <b>{a.title}</b>
                        <span className={"net " + (a.saves - a.cost > 0 ? "good" : a.saves - a.cost < 0 ? "bad" : "")}>
                          {a.cost > 0 || a.saves > 0 ? `${a.saves - a.cost >= 0 ? "-" : "+"}${Math.abs(a.saves - a.cost)} points` : "no change"}
                        </span>
                      </div>
                      <p>{a.detail}</p>
                      {!a.allowed && <small className="warn">Not allowed under rulebook {result.scenario}.</small>}
                      {a.cost > 0 && <small className="hint">Costs {a.cost}, saves {a.saves}.</small>}
                    </div>
                  ))}
                  <div className="alt-actions">
                    <button onClick={() => onSelect(c.activity_id)}>Open {c.activity_id}</button>
                    {c.holders.slice(0, 2).map((h) => (
                      <button key={h.activity_id} onClick={() => onSelect(h.activity_id)}>Open {h.activity_id}</button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {conflicts.length > 8 && (
        <button onClick={() => setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show all ${conflicts.length}`}</button>
      )}
    </div>
  );
}
