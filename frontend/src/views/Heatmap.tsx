// "Track spots by week" — one row per bookable location, one column per week.
// The number in a cell is the backend's `used` from result.capacity_usage; the
// colour compares it with that location's supply. No capacity is computed here.

import { Fragment, useMemo, useState } from "react";
import type { SolveResult } from "../types";
import {
  HEAT_WORDS,
  buildIndex,
  cellKey,
  fmtDayMonth,
  groupLocations,
  heatLevel,
  locationLabel,
  num,
  weekRangeLabel,
  weekStart,
} from "../lib/grid";
import "./grid.css";

export type HeatmapProps = {
  result: SolveResult;
  weeks: number[]; // the week numbers to show, ascending (already range-filtered)
  onSelect: (activityId: string) => void; // clicking an occupant opens the explain panel
};

const MAX_ROWS = 100;
/** Extra glyphs so "full" and "over" are not colour-only. */
const GLYPH: Record<number, string> = { 3: "◼", 4: "▲" };

export function Heatmap({ result, weeks, onSelect }: HeatmapProps) {
  const idx = useMemo(() => buildIndex(result), [result]);
  const [cell, setCell] = useState<{ locationId: string; week: number } | null>(null);

  const all = useMemo(() => result.instance.locations ?? [], [result]);
  const shown = useMemo(() => (all.length > MAX_ROWS ? all.slice(0, MAX_ROWS) : all), [all]);
  const groups = useMemo(() => groupLocations(shown, idx.lineNames), [shown, idx.lineNames]);
  const horizon = idx.horizonStart;

  const occupants = cell ? (idx.occupancyByCell.get(cellKey(cell.locationId, cell.week)) ?? []) : [];

  // Weekly limits, read off the data so hidden instances describe themselves.
  const limits = useMemo(() => {
    const seen = new Map<number, number>();
    for (const l of all) {
      const cap = num(l.supply_capacity);
      seen.set(cap, (seen.get(cap) ?? 0) + 1);
    }
    return [...seen.entries()].sort((a, b) => b[0] - a[0]);
  }, [all]);

  return (
    <div className="grid-card">
      <div className="legend-box">
        <ul className="grid-legend">
          {HEAT_WORDS.map((word, level) => (
            <li key={word}>
              <span className={"sw heat" + level} aria-hidden="true">
                {GLYPH[level] ?? ""}
              </span>{" "}
              {word}
            </li>
          ))}
        </ul>
        <ul className="grid-legend limits">
          <li className="legend-title">Weekly limits</li>
          {limits.map(([cap, count]) => (
            <li key={cap}>
              <b>{cap}</b> per week · {count} {count === 1 ? "spot" : "spots"}
              {cap === idx.minSupply ? " (tightest)" : ""}
            </li>
          ))}
        </ul>
        <p className="grid-hint">
          Lowest-capacity rows are the bottleneck. EB and WB are separate tracks and are booked separately.
          The number is bookings that week; the colour compares it with the limit in brackets.
        </p>
      </div>

      {cell && (
        <div className="cell-detail">
          <b>
            {locationLabel(cell.locationId)}, {weekRangeLabel(horizon, cell.week)}
          </b>
          {occupants.length === 0 ? (
            <span className="grid-hint">nothing booked here.</span>
          ) : (
            occupants.map((o) => (
              <button
                key={o.activity_id + o.co_share_group}
                type="button"
                className="chip"
                onClick={() => onSelect(o.activity_id)}
                title={`Open ${o.activity_id} · shares possession slot ${o.co_share_group}`}
              >
                {o.activity_id} <small>slot {o.co_share_group}</small>
              </button>
            ))
          )}
          <button type="button" className="chip chip-close" onClick={() => setCell(null)}>
            Close
          </button>
        </div>
      )}

      {all.length > MAX_ROWS && (
        <p className="grid-hint">
          Showing {MAX_ROWS} of {all.length} spots.
        </p>
      )}

      <div className="grid-scroll">
        <table className="grid-table heat-table">
          <thead>
            <tr>
              <th scope="col" className="grid-head-cell grid-sticky-col">
                Spot (limit)
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
            {groups.map((g) => (
              <Fragment key={g.key}>
                <tr className="group-row">
                  <th scope="colgroup" className="grid-sticky-col" colSpan={weeks.length + 1}>
                    {g.title}
                  </th>
                </tr>
                {g.rows.map((l) => {
                  const supply = num(l.supply_capacity);
                  const isHub = idx.hubLocations.has(l.location_id);
                  return (
                    <tr key={l.location_id} className={isHub ? "hub-row" : ""}>
                      <th scope="row" className="grid-sticky-col" title={l.location_id}>
                        {isHub && (
                          <span className="hub-mark" title="Interchange: this spot is shared between lines">
                            ◆
                          </span>
                        )}
                        <span className="spot-name">{locationLabel(l.location_id)}</span>
                        <small className="spot-cap">(limit {supply})</small>
                      </th>
                      {weeks.map((w) => {
                        const usage = idx.usageByCell.get(cellKey(l.location_id, w));
                        const used = num(usage?.used);
                        const level = heatLevel(used, supply);
                        const isPicked = cell?.locationId === l.location_id && cell?.week === w;
                        const label = `${locationLabel(l.location_id)}, week ${w}: ${used} of ${supply} booked — ${HEAT_WORDS[level]}`;
                        return (
                          <td
                            key={w}
                            className={"heat heat" + level + (isPicked ? " is-picked" : "")}
                          >
                            {used > 0 ? (
                              <button
                                type="button"
                                className="heat-btn"
                                title={label}
                                aria-label={label}
                                onClick={() => setCell({ locationId: l.location_id, week: w })}
                              >
                                <span className="heat-num">{used}</span>
                                {GLYPH[level] ? (
                                  <span className="heat-glyph" aria-hidden="true">
                                    {GLYPH[level]}
                                  </span>
                                ) : null}
                              </button>
                            ) : null}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <p className="grid-hint">
        ◆ marks an interchange spot, shared between lines — those rows have the smallest limits and fill up
        first. Click a number to see which jobs are in that slot.
      </p>
    </div>
  );
}
