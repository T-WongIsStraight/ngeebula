// STEP 2: choose which rulebook the planner follows.
// Each card shows, at a glance, what the rulebook allows and what it charges.

import type { Scenario } from "./types";
import { POINTS } from "./types";

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
    oneLine: "Never overbook. Jobs may finish late.",
    late: { text: "Allowed, costs points", kind: "cost" },
    eclo: { text: "Not allowed", kind: "no" },
    extra: { text: "Not allowed", kind: "no" },
    useWhen: "Track time cannot be stretched. No extra nights, no early closures.",
    example: "Two jobs want the hub tunnel in week 10. One moves to week 11 and its contract is 7 days late.",
  },
  {
    id: "B",
    title: "B · Deadlines fixed",
    oneLine: "Never finish late. Buy track time instead.",
    late: { text: "Not allowed", kind: "no" },
    eclo: { text: `${POINTS.ECLO} points each`, kind: "cost" },
    extra: { text: `${POINTS.EXCESS} points each, no cap`, kind: "cost" },
    useWhen: "Contract dates are non-negotiable. Score shows what hitting them costs.",
    example: "Both jobs stay in week 10. The hub tunnel is 1 over its limit, so the plan pays 7 points instead of being late.",
  },
  {
    id: "C",
    title: "C · Balanced",
    oneLine: "A little of both. Cheapest mix wins.",
    late: { text: "Allowed, costs points", kind: "cost" },
    eclo: { text: `${POINTS.ECLO} points each`, kind: "cost" },
    extra: { text: `${POINTS.EXCESS} points each, max 1 per spot per week`, kind: "cost" },
    useWhen: "Normal operations. Some slack exists, some dates can slip a little.",
    example: "A Priority 1 job would be a week late (700 points). One ECLO night (5 points) fixes it, so the planner uses ECLO.",
  },
];

function Pill({ a }: { a: Allow }) {
  return <span className={"pill " + a.kind}>{a.text}</span>;
}

type Props = { scenario: Scenario; onChange: (s: Scenario) => void; onBack: () => void; onBuild: () => void };

export function Step2Rules({ scenario, onChange, onBack, onBuild }: Props) {
  const chosen = RULES.find((r) => r.id === scenario)!;
  return (
    <div>
      <div className="card">
        <h2>Choose the planning rules</h2>
        <p className="lead">Pick the rulebook that matches how much flexibility you really have.</p>
        <div className="scenarios">
          {RULES.map((r) => (
            <label key={r.id} className={scenario === r.id ? "selected" : ""}>
              <input type="radio" checked={scenario === r.id} onChange={() => onChange(r.id)} />
              <b>{r.title}</b>
              <span>{r.oneLine}</span>
              <dl className="allow">
                <dt>Finishing late</dt><dd><Pill a={r.late} /></dd>
                <dt>ECLO nights</dt><dd><Pill a={r.eclo} /></dd>
                <dt>Extra nights</dt><dd><Pill a={r.extra} /></dd>
              </dl>
            </label>
          ))}
        </div>
      </div>

      <div className="card why">
        <h2>Why {chosen.id}?</h2>
        <ul className="why-list">
          <li><b>Use when</b> {chosen.useWhen}</li>
          <li><b>Example</b> {chosen.example}</li>
          <li><b>Late day costs</b> {POINTS.LATE["1"]} points for Priority 1, {POINTS.LATE["2"]} for Priority 2, {POINTS.LATE["3"]} for Priority 3. Lower total score is better.</li>
        </ul>
      </div>

      <div className="stepnav">
        <button onClick={onBack}>Back</button>
        <button className="primary" onClick={onBuild}>Build the schedule</button>
      </div>
    </div>
  );
}
