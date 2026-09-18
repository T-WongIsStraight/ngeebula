// The whole app: a 3-step flow. Load files -> choose rules -> see the schedule.

import { useState } from "react";
import { StepTrain } from "./StepTrain";
import { Step1Upload } from "./Step1Upload";
import { Step2Rules } from "./Step2Rules";
import { ResultScreen } from "./ResultScreen";
import { Loading } from "./Loading";
import { ThemeToggle } from "./ThemeToggle";
import { fakeSolve } from "./fakeSolver";
import type { Instance } from "./csv";
import type { Scenario, SolveResult } from "./types";

export default function App() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [instance, setInstance] = useState<Instance | null>(null);
  const [scenario, setScenario] = useState<Scenario>("A");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SolveResult | null>(null);

  async function build() {
    if (!instance) return;
    setRunning(true);
    const r = await fakeSolve(scenario, instance); // later: fetch("/api/solve", ...)
    setResult(r);
    setRunning(false);
    setStep(3);
    window.scrollTo({ top: 0 });
  }

  return (
    <main>
      <ThemeToggle />
      <header>
        <h1>Track Access Scheduler</h1>
        <p>Plans which contractor works on which stretch of track, each week, without breaking safety rules.</p>
      </header>

      <StepTrain step={step} />

      {running && <Loading scenario={scenario} />}

      {step === 1 && <Step1Upload instance={instance} onLoaded={setInstance} onNext={() => setStep(2)} />}
      {step === 2 && <Step2Rules scenario={scenario} onChange={setScenario} onBack={() => setStep(1)} onBuild={build} />}
      {step === 3 && result && (
        <ResultScreen result={result} onUpdate={setResult} onBack={() => setStep(2)} onRestart={() => { setResult(null); setInstance(null); setStep(1); }} />
      )}
    </main>
  );
}
