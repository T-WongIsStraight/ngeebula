// "Jobs by week" — one column per week, one row per contract (folded) or job (open).
// A filled dot = one night of work that week. Everything shown is read from the
// backend payload: nights from schedule_access, lateness from results, deadline
// from the contract's planned_completion_date. Nothing is scored here.

import { Fragment, useMemo, useState } from "react";
import type { SolveResult } from "../types";
import {
  buildIndex,
  fmtDate,
  fmtDayMonth,
  lateLabel,
  num,
  sortedContracts,
  weekEnd,
  weekOfDate,
  weekRangeLabel,
  weekStart,
  activityWeekKey,
} from "../lib/grid";
import "./grid.css";

export type TimelineProps = {
  result: SolveResult;
  weeks: number[]; // the week numbers to show, ascending (already range-filtered)
  selected: string | null; // activity_id highlighted
  onSelect: (activityId: string) => void;
};

export function Timeline({ result, weeks, selected, onSelect }: TimelineProps) {
  const idx = useMemo(() => buildIndex(result), [result]);
  // Folded by default so all contracts fit on one screen at 2 AM.
  const [open, setOpen] = useState<ReadonlySet<string>>(() => new Set<string>());

  const toggle = (contractNumber: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(contractNumber)) next.delete(contractNumber);
      else next.add(contractNumber);
      return next;
    });

  const contracts = useMemo(() => sortedContracts(result.instance.contracts ?? []), [result]);
  const horizon = idx.horizonStart;

  return (
    <div className="grid-card">
      <div className="grid-scroll">
        <table className="grid-table timeline-table">
          <thead>
            <tr>
              <th scope="col" className="grid-head-cell grid-sticky-col">
                Contract / job
              </th>
              {weeks.map((w) => (
                <th key={w} scope="col" className="grid-head-cell wk" title={weekRangeLabel(horizon, w)}>
                  <span className="wk-num">{w}</span>
                  <small>{fmtDayMonth(weekStart(horizon, w))}</small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {contracts.map((c) => {
              const jobs = idx.activitiesByContract.get(c.contract_number) ?? [];
              const isOpen = open.has(c.contract_number);
              const outcome = lateLabel(idx.resultByContract.get(c.contract_number));
              const deadlineWeek = weekOfDate(horizon, c.planned_completion_date);
              const span = idx.spanByContract.get(c.contract_number);
              const priority = c.contract_priority || "3";

              return (
                <Fragment key={c.contract_number}>
                  <tr className={"contract-row" + (isOpen ? " is-open" : "")}>
                    <th scope="row" className="grid-sticky-col">
                      <button
                        type="button"
                        className="fold"
                        aria-expanded={isOpen}
                        onClick={() => toggle(c.contract_number)}
                        title={
                          `${c.contract_number}${c.contract_description ? " — " + c.contract_description : ""}` +
                          `\nDeadline ${c.planned_completion_date}` +
                          (deadlineWeek ? ` (week ${deadlineWeek})` : "")
                        }
                      >
                        <span className="caret" aria-hidden="true">
                          {isOpen ? "−" : "+"}
                        </span>
                        <span className={"pri p" + priority}>P{priority}</span>
                        <span className="cname">{c.contract_number}</span>
                        <small className="cjobs">
                          {jobs.length} {jobs.length === 1 ? "job" : "jobs"}
                        </small>
                        <span className={"tag " + (outcome.late > 0 ? "tag-late" : "tag-ok")}>{outcome.text}</span>
                      </button>
                    </th>
                    {weeks.map((w) => {
                      const inSpan = span ? w >= span[0] && w <= span[1] : false;
                      const cls =
                        (inSpan ? "span" : "") +
                        (span && w === span[0] ? " span-start" : "") +
                        (span && w === span[1] ? " span-end" : "") +
                        (w === deadlineWeek ? " deadline" : "");
                      return (
                        <td
                          key={w}
                          className={cls.trim()}
                          title={
                            w === deadlineWeek
                              ? `Deadline: ${fmtDate(weekEnd(horizon, w))} (${c.planned_completion_date})`
                              : inSpan
                                ? `${c.contract_number} is working somewhere between weeks ${span?.[0]} and ${span?.[1]}`
                                : undefined
                          }
                        >
                          {inSpan ? <span className="spanbar" aria-hidden="true" /> : null}
                        </td>
                      );
                    })}
                  </tr>

                  {isOpen &&
                    jobs.map((a) => {
                      const jobSpan = idx.spanByActivity.get(a.activity_id);
                      const isSelected = selected === a.activity_id;
                      return (
                        <tr key={a.activity_id} className={"job-row" + (isSelected ? " is-selected" : "")}>
                          <th scope="row" className="grid-sticky-col">
                            <button
                              type="button"
                              className="jobbtn"
                              aria-pressed={isSelected}
                              onClick={() => onSelect(a.activity_id)}
                              title={`${a.activity_id}: ${a.start_location_id} → ${a.end_location_id}\nClick to see why it is on these weeks`}
                            >
                              <span className="indent" aria-hidden="true" />
                              <span className="jname">{a.activity_id}</span>
                              <small className="jnights">
                                {num(a.total_accesses)} {num(a.total_accesses) === 1 ? "night" : "nights"}
                              </small>
                            </button>
                          </th>
                          {weeks.map((w) => {
                            const night = idx.accessByActivityWeek.get(activityWeekKey(a.activity_id, w));
                            const isEclo = night ? num(night.eclo) === 1 : false;
                            const waiting =
                              !night && jobSpan !== undefined && w > jobSpan[0] && w < jobSpan[1];
                            const cls = w === deadlineWeek ? "deadline" : "";
                            if (night) {
                              return (
                                <td key={w} className={cls}>
                                  <span
                                    className={"dot p" + priority + (isEclo ? " eclo" : "")}
                                    title={
                                      `${a.activity_id} works ${weekRangeLabel(horizon, w)}` +
                                      `\nNight slot ${num(night.access_night)} of the contract's weekly allowance` +
                                      `\nNight ${num(night.access_seq)} of ${num(a.total_accesses)}` +
                                      (isEclo ? "\nECLO: a longer night (counts 1.5)" : "")
                                    }
                                  >
                                    {isEclo ? "E" : ""}
                                  </span>
                                </td>
                              );
                            }
                            return (
                              <td key={w} className={cls}>
                                {waiting ? (
                                  <span
                                    className="dot wait"
                                    title={`${a.activity_id} is waiting in ${weekRangeLabel(horizon, w)} — it works before and after, but not this week`}
                                  >
                                    <span className="sr-only">waiting</span>
                                  </span>
                                ) : null}
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
      </div>

      <ul className="grid-legend">
        <li>
          <span className="dot p1" aria-hidden="true" /> Priority 1 night
        </li>
        <li>
          <span className="dot p2" aria-hidden="true" /> Priority 2 night
        </li>
        <li>
          <span className="dot p3" aria-hidden="true" /> Priority 3 night
        </li>
        <li>
          <span className="dot p3 eclo" aria-hidden="true">
            E
          </span>{" "}
          ECLO (longer night)
        </li>
        <li>
          <span className="dot wait" aria-hidden="true" /> waiting (no work that week)
        </li>
        <li>
          <span className="dl-swatch" aria-hidden="true" /> deadline week
        </li>
      </ul>
      <p className="grid-hint">
        Each dot is one night of work. Click a contract to open its jobs; click a job to see why it sits on
        those weeks. The bar on a contract row runs from its first working week to its last.
      </p>
    </div>
  );
}
