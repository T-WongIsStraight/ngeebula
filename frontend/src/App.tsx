// The whole app: load files -> choose rules -> watch it run -> read the
// schedule. All the thinking happens on the server; this page moves files up
// and shows what comes back.

import { useCallback, useRef, useState } from "react";
import { ApiError, pollJob, solve } from "./api";
import { acceptFiles, loadSampleFiles } from "./lib/instanceFiles";
import type { FileCheck } from "./lib/instanceFiles";
import type { InstanceSummary } from "./lib/summary";
import { INSTANCE_FILES } from "./types";
import type { Job, Scenario, SolveResult } from "./types";
import { StepTrain } from "./steps/StepTrain";
import type { StepNumber } from "./steps/StepTrain";
import { Step1Upload } from "./steps/Step1Upload";
import { Step2Rules } from "./steps/Step2Rules";
import { Running } from "./steps/Running";
import { Failed } from "./steps/Failed";
import type { FailureKind } from "./steps/Failed";
import { ResultScreen } from "./steps/ResultScreen";
import { ThemeToggle } from "./steps/ThemeToggle";

type Phase = "upload" | "rules" | "running" | "result" | "failed";

type Failure = { kind: FailureKind; message: string; errorCode?: string };

const EMPTY_CHECKS: FileCheck[] = INSTANCE_FILES.map((name) => ({
  name,
  status: "missing",
  detail: "not chosen yet",
}));

const STEP_OF: Record<Phase, StepNumber> = {
  upload: 1,
  rules: 2,
  running: 3,
  result: 3,
  failed: 3,
};

export default function App() {
  const [phase, setPhase] = useState<Phase>("upload");

  // Step 1 state
  const [files, setFiles] = useState<Record<string, File>>({});
  const [checks, setChecks] = useState<FileCheck[]>(EMPTY_CHECKS);
  const [summary, setSummary] = useState<InstanceSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  // Step 2 state
  const [scenario, setScenario] = useState<Scenario>("A");
  const [timeLimit, setTimeLimit] = useState(60);

  // Run state
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [startedAt, setStartedAt] = useState(0);
  const [result, setResult] = useState<SolveResult | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const abort = useRef<AbortController | null>(null);

  const go = useCallback((next: Phase) => {
    setPhase(next);
    window.scrollTo({ top: 0 });
  }, []);

  const takeFiles = useCallback(
    async (base: Record<string, File>, incoming: File[]) => {
      if (incoming.length === 0) return;
      setBusy(true);
      setProblem(null);
      try {
        const r = await acceptFiles(base, incoming);
        setFiles(r.accepted);
        setChecks(r.checks);
        setSummary(r.summary);
        if (r.extras.length > 0) {
          setProblem(
            `Ignored ${r.extras.length} file${r.extras.length === 1 ? "" : "s"} that ${
              r.extras.length === 1 ? "is" : "are"
            } not one of the 8: ${r.extras.slice(0, 6).join(", ")}${r.extras.length > 6 ? "…" : ""}`,
          );
        }
      } catch {
        setProblem("Could not read those files. Make sure they are the plain CSV files, not a zip or a spreadsheet.");
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const onFiles = useCallback((incoming: File[]) => void takeFiles(files, incoming), [files, takeFiles]);

  const onSample = useCallback(() => {
    setBusy(true);
    setProblem(null);
    loadSampleFiles()
      .then((sample) => takeFiles({}, sample))
      .catch(() => {
        setProblem("Could not read the bundled sample instance. Reload the page and try again.");
        setBusy(false);
      });
  }, [takeFiles]);

  const onClear = useCallback(() => {
    setFiles({});
    setChecks(EMPTY_CHECKS);
    setSummary(null);
    setProblem(null);
  }, []);

  const build = useCallback(async () => {
    const ordered = INSTANCE_FILES.map((n) => files[n]).filter((f): f is File => Boolean(f));
    if (ordered.length !== INSTANCE_FILES.length) {
      go("upload");
      setProblem("Some files went missing. Load all 8 again.");
      return;
    }

    const controller = new AbortController();
    abort.current = controller;
    setJob(null);
    setJobId(null);
    setResult(null);
    setFailure(null);
    setStartedAt(Date.now());
    go("running");

    try {
      const { job_id } = await solve(ordered, scenario, timeLimit);
      setJobId(job_id);
      const finished = await pollJob(job_id, setJob, controller.signal);

      if (finished.status === "done" && finished.result) {
        setResult(finished.result);
        go("result");
        return;
      }
      if (finished.status === "infeasible" || finished.status === "timeout") {
        setFailure({ kind: finished.status, message: finished.message, errorCode: finished.error_code });
      } else {
        setFailure({
          kind: "error",
          message: finished.message || "The job finished without producing a schedule.",
          errorCode: finished.error_code,
        });
      }
      go("failed");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return; // the user pressed Stop watching
      const apiError = err instanceof ApiError ? err : null;
      setFailure({
        kind: "error",
        message: apiError?.message ?? "Something went wrong while talking to the scheduling server.",
        errorCode: apiError?.errorCode,
      });
      go("failed");
    } finally {
      if (abort.current === controller) abort.current = null;
    }
  }, [files, go, scenario, timeLimit]);

  const cancel = useCallback(() => {
    abort.current?.abort();
    abort.current = null;
    go("rules");
  }, [go]);

  const restart = useCallback(() => {
    abort.current?.abort();
    abort.current = null;
    onClear();
    setJob(null);
    setJobId(null);
    setResult(null);
    setFailure(null);
    setScenario("A");
    setTimeLimit(60);
    go("upload");
  }, [go, onClear]);

  return (
    <main>
      <ThemeToggle />
      <header>
        <h1>Track Access Scheduler</h1>
        <p>
          Plans which contractor works on which stretch of track, each week, without breaking a safety rule or a
          deadline more than it has to.
        </p>
      </header>

      <StepTrain step={STEP_OF[phase]} />

      {phase === "upload" && (
        <Step1Upload
          checks={checks}
          summary={summary}
          busy={busy}
          problem={problem}
          onFiles={onFiles}
          onSample={onSample}
          onClear={onClear}
          onNext={() => go("rules")}
        />
      )}

      {phase === "rules" && (
        <Step2Rules
          scenario={scenario}
          timeLimit={timeLimit}
          onScenario={setScenario}
          onTimeLimit={setTimeLimit}
          onBack={() => go("upload")}
          onBuild={() => void build()}
        />
      )}

      {phase === "running" && (
        <Running scenario={scenario} timeLimit={timeLimit} job={job} startedAt={startedAt} onCancel={cancel} />
      )}

      {phase === "failed" && failure && (
        <Failed
          kind={failure.kind}
          message={failure.message}
          errorCode={failure.errorCode}
          scenario={scenario}
          timeLimit={timeLimit}
          onBack={() => go("rules")}
          onRestart={restart}
        />
      )}

      {phase === "result" && result && jobId && (
        <ResultScreen result={result} jobId={jobId} onBack={() => go("rules")} onRestart={restart} />
      )}
    </main>
  );
}
