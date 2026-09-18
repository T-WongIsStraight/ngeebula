// Shown while the scheduler runs: a train going round a loop, the time so far,
// and whatever the server last said. Cancelling only stops us watching — the
// solve carries on server-side.

import { useEffect, useState } from "react";
import type { Job, Scenario } from "../types";

type Props = {
  scenario: Scenario;
  timeLimit: number;
  job: Job | null;
  startedAt: number;
  onCancel: () => void;
};

export function Running({ scenario, timeLimit, job, startedAt, onCancel }: Props) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  const elapsed = Math.max(0, Math.round((now - startedAt) / 1000));

  return (
    <div className="loading" role="status" aria-live="polite">
      <svg className="loop" viewBox="0 0 240 140" width="240" height="140" aria-hidden="true">
        <rect x="20" y="20" width="200" height="100" rx="50" fill="none" stroke="var(--border)" strokeWidth="6" />
        <rect
          x="20"
          y="20"
          width="200"
          height="100"
          rx="50"
          fill="none"
          stroke="var(--muted)"
          strokeWidth="2"
          strokeDasharray="4 10"
        />
        <circle cx="120" cy="20" r="5" fill="var(--surface-2)" stroke="var(--muted)" strokeWidth="2" />
        <circle cx="120" cy="120" r="5" fill="var(--surface-2)" stroke="var(--muted)" strokeWidth="2" />
        <circle cx="20" cy="70" r="5" fill="var(--surface-2)" stroke="var(--muted)" strokeWidth="2" />
        <circle cx="220" cy="70" r="5" fill="var(--surface-2)" stroke="var(--muted)" strokeWidth="2" />
        {["c1", "c2", "c3"].map((c, i) => (
          <g className={"car " + c} key={c}>
            <rect x="-14" y="-7" width="28" height="14" rx="4" fill="var(--accent)" opacity={1 - i * 0.15} />
            <rect x="-9" y="-4" width="6" height="5" rx="1" fill="#fff" opacity=".85" />
            <rect x="3" y="-4" width="6" height="5" rx="1" fill="#fff" opacity=".85" />
          </g>
        ))}
      </svg>

      <h2>Building the schedule for Scenario {scenario}</h2>
      <p className="elapsed">
        {elapsed}s <small>of up to {timeLimit}s</small>
      </p>
      <p className="hint">{job?.message ?? "Sending the files to the scheduler…"}</p>
      {job?.solver_status && <p className="hint">Solver: {job.solver_status}</p>}
      <p className="hint">Placing every job across the whole period and checking each safety rule.</p>

      <button type="button" onClick={onCancel}>
        Stop watching
      </button>
      <p className="hint small">
        This only takes you back to the rules. The scheduler keeps running on the server, so you can start again
        straight away.
      </p>
    </div>
  );
}
