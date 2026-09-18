// Progress bar drawn like a train line: 3 stations, the train sits at the step
// you are on.

const STEPS = ["Load files", "Choose rules", "Schedule"] as const;

export type StepNumber = 1 | 2 | 3;

export function StepTrain({ step }: { step: StepNumber }) {
  return (
    <nav className="steptrain" aria-label="Progress">
      <div className="track" />
      <div className="track done" style={{ width: `${((step - 1) / 2) * 100}%` }} />
      {STEPS.map((label, i) => {
        const n = (i + 1) as StepNumber;
        const state = n < step ? "done" : n === step ? "current" : "todo";
        return (
          <div key={label} className={"station " + state} style={{ left: `${(i / 2) * 100}%` }}>
            <div className="dot" aria-current={n === step ? "step" : undefined}>
              {n < step ? "✓" : n}
            </div>
            <div className="label">
              <b>Step {n}</b>
              <span>{label}</span>
            </div>
          </div>
        );
      })}
      <div className="train" style={{ left: `${((step - 1) / 2) * 100}%` }} aria-hidden="true">
        <svg viewBox="0 0 40 20" width="40" height="20">
          <rect x="2" y="3" width="36" height="14" rx="4" fill="var(--accent)" />
          <rect x="7" y="7" width="7" height="6" rx="1" fill="#fff" opacity=".9" />
          <rect x="17" y="7" width="7" height="6" rx="1" fill="#fff" opacity=".9" />
          <rect x="27" y="7" width="7" height="6" rx="1" fill="#fff" opacity=".9" />
        </svg>
      </div>
    </nav>
  );
}
