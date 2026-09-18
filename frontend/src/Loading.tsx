// Full-screen overlay shown while the solver runs: a train looping around a track.

export function Loading({ scenario }: { scenario: string }) {
  return (
    <div className="loading">
      <svg className="loop" viewBox="0 0 240 140" width="240" height="140" aria-hidden="true">
        {/* the track: a rounded loop */}
        <rect x="20" y="20" width="200" height="100" rx="50" fill="none" stroke="var(--line)" strokeWidth="6" />
        <rect x="20" y="20" width="200" height="100" rx="50" fill="none" stroke="var(--muted)" strokeWidth="2" strokeDasharray="4 10" />
        {/* stations */}
        <circle cx="120" cy="20" r="5" fill="var(--card2)" stroke="var(--muted)" strokeWidth="2" />
        <circle cx="120" cy="120" r="5" fill="var(--card2)" stroke="var(--muted)" strokeWidth="2" />
        <circle cx="20" cy="70" r="5" fill="var(--card2)" stroke="var(--muted)" strokeWidth="2" />
        <circle cx="220" cy="70" r="5" fill="var(--card2)" stroke="var(--muted)" strokeWidth="2" />
        {/* the train: three carriages following the same loop, offset in time */}
        <g className="car c1"><rect x="-14" y="-7" width="28" height="14" rx="4" fill="var(--accent)" /><rect x="-9" y="-4" width="6" height="5" rx="1" fill="#fff" opacity=".85" /><rect x="3" y="-4" width="6" height="5" rx="1" fill="#fff" opacity=".85" /></g>
        <g className="car c2"><rect x="-14" y="-7" width="28" height="14" rx="4" fill="var(--accent)" opacity=".85" /><rect x="-9" y="-4" width="6" height="5" rx="1" fill="#fff" opacity=".85" /><rect x="3" y="-4" width="6" height="5" rx="1" fill="#fff" opacity=".85" /></g>
        <g className="car c3"><rect x="-14" y="-7" width="28" height="14" rx="4" fill="var(--accent)" opacity=".7" /><rect x="-9" y="-4" width="6" height="5" rx="1" fill="#fff" opacity=".85" /><rect x="3" y="-4" width="6" height="5" rx="1" fill="#fff" opacity=".85" /></g>
      </svg>
      <h2>Building the schedule for Scenario {scenario}</h2>
      <p className="hint">Placing 54 jobs across 30 weeks and checking every safety rule.</p>
    </div>
  );
}
