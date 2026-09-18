// Track spots by week: rows are the 76 bookable spots, columns are weeks.
// Number in a cell = bookings that week. Colour = bookings compared to that spot's weekly limit.
// Click a cell to see which jobs are in it.

import { Fragment, useState } from "react";
import type { SolveResult, Location } from "./types";
import { bookingsPerSpotWeek, spotLabel, weekLabel } from "./schedule";

type Props = { result: SolveResult; weeks: number[]; onSelect: (activityId: string) => void };

// 0 = empty, 1 = some room, 2 = nearly full, 3 = full, 4 = over the limit
function level(n: number, limit: number): number {
  if (n === 0) return 0;
  if (n > limit) return 4;
  if (n === limit) return 3;
  return n / limit >= 0.5 ? 2 : 1;
}

// The weekly limits, read from the data: one line per kind of spot
function limitRules(locations: Location[]): { label: string; limit: number }[] {
  const seen = new Map<string, number>();
  for (const l of locations) {
    const hub = l.location_id.includes("H01_H02") || /:(H01|H02):/.test(l.location_id);
    const nearHub = !hub && /(H01|H02)/.test(l.location_id);
    const kind = l.location_kind === "tunnel sector" ? "Tunnel" : "Station platform";
    const label = hub ? `Hub ${kind.toLowerCase()} (H01, H02)` : nearHub ? `${kind} next to a hub` : kind;
    seen.set(label, Number(l.supply_capacity));
  }
  return [...seen].map(([label, limit]) => ({ label, limit })).sort((a, b) => b.limit - a.limit);
}

export function Heatmap({ result, weeks, onSelect }: Props) {
  const [cell, setCell] = useState<{ loc: string; week: number } | null>(null);
  const used = bookingsPerSpotWeek(result.occupancy);

  const groups: { title: string; spots: Location[] }[] = [];
  for (const line of ["ALP", "BET"]) {
    for (const kind of ["tunnel sector", "platform sector"]) {
      groups.push({
        title: `Line ${line === "ALP" ? "Alpha" : "Beta"} · ${kind === "tunnel sector" ? "tunnels" : "station platforms"}`,
        spots: result.locations.filter((l) => l.line_code === line && l.location_kind === kind),
      });
    }
  }

  const jobsInCell = cell ? result.occupancy.filter((o) => o.location_id === cell.loc && Number(o.week) === cell.week) : [];

  return (
    <div>
      <div className="legend-box">
        <div className="legend">
          <span><i className="sw h0" /> empty</span>
          <span><i className="sw h1" /> some room</span>
          <span><i className="sw h2" /> nearly full</span>
          <span><i className="sw h3" /> full</span>
          <span><i className="sw h4" /> over the limit</span>
        </div>
        <div className="legend limits">
          <span className="legend-title">Weekly limits</span>
          {limitRules(result.locations).map((r) => (
            <span key={r.label}><b>{r.limit}</b> {r.label}</span>
          ))}
        </div>
        <p className="hint">EB = eastbound rail, WB = westbound rail. Each rail is booked separately. Number = bookings that week. Colour = number compared to the limit in brackets.</p>
      </div>

      {cell && (
        <div className="cell-detail">
          <b>{spotLabel(cell.loc)}, week {cell.week}</b>: {jobsInCell.length === 0 ? "nothing booked." : ""}
          {jobsInCell.map((o) => (
            <button key={o.activity_id} className="chip" onClick={() => onSelect(o.activity_id)}>
              {o.activity_id} <small>slot {o.co_share_group}</small>
            </button>
          ))}
          <button className="chip" onClick={() => setCell(null)}>Close</button>
        </div>
      )}

      <div className="timeline">
        <table>
          <thead>
            <tr>
              <th className="sticky">Spot (limit)</th>
              {weeks.map((w) => (
                <th key={w} title={`Week ${w} starts ${weekLabel(result.horizonStart, w)}`}>
                  {w}<small>{weekLabel(result.horizonStart, w)}</small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <Fragment key={g.title}>
                <tr className="contract-row">
                  <td className="sticky" colSpan={weeks.length + 1}>{g.title}</td>
                </tr>
                {g.spots.map((l) => {
                  const limit = Number(l.supply_capacity);
                  return (
                    <tr key={l.location_id} className={l.location_id.includes("H01_H02") ? "hub" : ""}>
                      <td className="sticky" title={l.location_id}>
                        {spotLabel(l.location_id)} <small>({limit})</small>
                      </td>
                      {weeks.map((w) => {
                        const n = used.get(`${l.location_id}|${w}`) ?? 0;
                        const isSel = cell?.loc === l.location_id && cell?.week === w;
                        return (
                          <td
                            key={w}
                            className={"heat h" + level(n, limit) + (isSel ? " selected" : "")}
                            title={`${spotLabel(l.location_id)} week ${w}: ${n} of ${limit} booked`}
                            onClick={() => setCell({ loc: l.location_id, week: w })}
                          >
                            {n > 0 ? n : ""}
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
      <p className="hint">The hub tunnel H01-H02 has a limit of 1 and is the bottleneck. Click a cell to see which jobs are in it.</p>
    </div>
  );
}
