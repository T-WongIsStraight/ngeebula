// STEP 2: choose which rulebook the scheduler follows, and how long it may
// think. Each card shows what the rulebook allows and what it charges.

import type { Scenario } from "../types";
import { POINTS } from "../types";

type Allow = { text: string; kind: "no" | "cost" | "free" };
type Rule = {
  id: Scenario;
  title: string;
  oneLine: string;
  late: Allow;
  eclo: Allow;
  extra: Allow;
  useWhen: string;
  example: string;
};

const RULES: Rule[] = [
  {
    id: "A",
    title: "A · Track limits fixed",
    oneLine: "Never overbook a spot. Jobs may finish late.",
    late: { text: "Allowed, costs points", kind: "cost" },
    eclo: { text: "Not allowed", kind: "no" },
    extra: { text: "Not allowed", kind: "no" },
    useWhen: "Track time cannot be stretched: no extra nights, no early closures.",
    example: "Two jobs want the hub tunnel in week 10. One moves to week 11 and its contract finishes 7 days late.",
  },
  {
    id: "B",
    title: "B · Deadlines fixed",
    oneLine: "Nobody finishes late. Buy track time instead.",
    late: { text: "Not allowed at all", kind: "no" },
    eclo: { text: `${POINTS.ECLO} points each`, kind: "cost" },
    extra: { text: `${POINTS.EXCESS} points each, no cap`, kind: "cost" },
    useWhen: "Contract dates are non-negotiable and you want to see what hitting them costs.",
    example: "Both jobs stay in week 10. The hub tunnel goes 1 over its limit, so the plan pays 7 points instead.",
  },
  {
    id: "C",
    title: "C · Balanced",
    oneLine: "A little of both. The cheapest mix wins.",
    late: { text: "Allowed, costs points", kind: "cost" },
    eclo: { text: `${POINTS.ECLO} points each`, kind: "cost" },
    extra: { text: `${POINTS.EXCESS} points each, max 1 per spot per week`, kind: "cost" },
    useWhen: "Normal operations: some slack exists and some dates can slip a little.",
    example: `A Priority 1 job would be a week late (about ${POINTS.LATE["1"] * 7} points). One longer night costs ${POINTS.ECLO}, so the scheduler uses the longer night.`,
  },
];

function Pill({ a }: { a: Allow }) {
  return <span className={"pill " + a.kind}>{a.text}</span>;
}

type Props = {
  scenario: Scenario;
  timeLimit: number;
  onScenario: (s: Scenario) => void;
  onTimeLimit: (n: number) => void;
  onBack: () => void;
  onBuild: () => void;
};

export function Step2Rules({ scenario, timeLimit, onScenario, onTimeLimit, onBack, onBuild }: Props) {
  const chosen = RULES.find((r) => r.id === scenario) ?? RULES[0];
  const validLimit = timeLimit >= 5 && timeLimit <= 300;

  return (
    <div>
      <div className="card">
        <h2>Choose the planning rules</h2>
        <p className="lead">Pick the rulebook that matches how much flexibility you really have tonight.</p>
        <div className="scenarios">
          {RULES.map((r) => (
            <label key={r.id} className={scenario === r.id ? "selected" : ""}>
              <input
                type="radio"
                name="scenario"
                checked={scenario === r.id}
                onChange={() => onScenario(r.id)}
              />
              <b>{r.title}</b>
              <span>{r.oneLine}</span>
              <dl className="allow">
                <dt>Finishing late</dt>
                <dd>
                  <Pill a={r.late} />
                </dd>
                <dt>Longer nights (ECLO)</dt>
                <dd>
                  <Pill a={r.eclo} />
                </dd>
                <dt>Extra nights over a spot's limit</dt>
                <dd>
                  <Pill a={r.extra} />
                </dd>
              </dl>
            </label>
          ))}
        </div>
      </div>

      <div className="card why">
        <h2>Why {chosen.id}?</h2>
        <ul className="why-list">
          <li>
            <b>Use when</b> {chosen.useWhen}
          </li>
          <li>
            <b>Example</b> {chosen.example}
          </li>
          <li>
            <b>Late day costs</b> {POINTS.LATE["1"]} points for a Priority 1 contract, {POINTS.LATE["2"]} for Priority
            2, {POINTS.LATE["3"]} for Priority 3, for every day past the deadline. A lower total score is better.
          </li>
        </ul>
      </div>

      <div className="card">
        <h2>How long may the scheduler think?</h2>
        <p className="lead">
          More time usually means a lower score. It stops early if it proves the answer cannot be beaten.
        </p>
        <div className="timelimit">
          <label>
            <span>Seconds</span>
            <input
              type="number"
              min={5}
              max={300}
              step={5}
              value={timeLimit}
              onChange={(e) => onTimeLimit(Number(e.target.value))}
            />
          </label>
          <span className="hint">Between 5 and 300. 60 is a good default for an instance this size.</span>
        </div>
        {!validLimit && <p className="bad-text">Enter a number of seconds between 5 and 300.</p>}
      </div>

      <div className="stepnav">
        <button type="button" onClick={onBack}>
          Back: change files
        </button>
        <button type="button" className="primary" disabled={!validLimit} onClick={onBuild}>
          Build the schedule
        </button>
      </div>
    </div>
  );
}
