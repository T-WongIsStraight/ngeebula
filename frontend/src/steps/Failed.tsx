// The run did not produce a schedule. One screen per reason, each with the
// server's own message and a plain-English next step.

import type { Scenario } from "../types";

export type FailureKind = "infeasible" | "timeout" | "error";

type Props = {
  kind: FailureKind;
  message: string;
  errorCode?: string;
  scenario: Scenario;
  timeLimit: number;
  onBack: () => void;
  onRestart: () => void;
};

export function Failed({ kind, message, errorCode, scenario, timeLimit, onBack, onRestart }: Props) {
  const heading =
    kind === "infeasible"
      ? "No schedule fits these rules"
      : kind === "timeout"
        ? "Ran out of time"
        : "The scheduler could not finish";

  const badge = kind === "timeout" ? "OUT OF TIME" : kind === "infeasible" ? "NO SCHEDULE" : "SOMETHING WENT WRONG";

  const nextSteps =
    kind === "infeasible"
      ? [
          `Scenario ${scenario} forbids the escape routes the scheduler needed. Scenario C allows one extra night per spot and longer nights; Scenario B allows as many extra nights as it takes.`,
          "Check 08_ACTIVITY_DETAILS.csv: a job whose planned start date leaves fewer weeks than it needs nights can never fit, because a job works at most one night a week.",
          "Check that every location used by a job appears in 04_LOCATION_SUPPLY.csv with a capacity above zero.",
        ]
      : kind === "timeout"
        ? [
            `The scheduler had ${timeLimit} seconds and had not found a schedule it could prove legal. Raise the time limit (up to 300 seconds) and run it again.`,
            "Larger instances need more time. If 300 seconds is not enough, try Scenario B or C, which give the scheduler more room to move.",
          ]
        : [
            "Run it again: the scheduling server may have restarted or been busy.",
            "If it keeps happening, check that the server is up and that the 8 files are the ones the judges gave you, unedited.",
          ];

  return (
    <div>
      <div className={"verdict " + (kind === "error" ? "badbox" : "failbox")}>
        <div className="verdict-badge">{badge}</div>
        <p>{heading}.</p>
      </div>

      <div className="card">
        <h2>What the server said</h2>
        <p className="server-message">{message || "No message was returned."}</p>
        {errorCode && (
          <p className="hint">
            Error code: <code>{errorCode}</code>
          </p>
        )}

        <h2>What to do next</h2>
        <ul className="why-list plain-list">
          {nextSteps.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </div>

      <div className="stepnav">
        <button type="button" className="primary" onClick={onBack}>
          Back: change rules and try again
        </button>
        <button type="button" onClick={onRestart}>
          Start over with new files
        </button>
      </div>
    </div>
  );
}
