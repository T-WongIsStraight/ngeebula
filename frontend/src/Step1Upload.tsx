// STEP 1: load the 8 planning files, check them, show what is inside.

import { useState } from "react";
import sample from "./data/sample.json";
import { REQUIRED_FILES, readInstanceFiles, summarise } from "./csv";
import type { Instance, FileCheck } from "./csv";

type Props = { instance: Instance | null; onLoaded: (inst: Instance | null) => void; onNext: () => void };

export function Step1Upload({ instance, onLoaded, onNext }: Props) {
  const [checks, setChecks] = useState<FileCheck[]>([]);
  const [busy, setBusy] = useState(false);

  async function pick(files: File[]) {
    setBusy(true);
    const r = await readInstanceFiles(files);
    setChecks(r.checks);
    onLoaded(r.instance);
    setBusy(false);
  }

  function useSample() {
    const inst = sample as unknown as Instance;
    setChecks(REQUIRED_FILES.map((f) => ({ name: f.name, status: "ok", detail: `${(inst[f.key] as unknown[]).length} rows (sample)` })));
    onLoaded(inst);
  }

  const s = instance ? summarise(instance) : null;
  const okCount = checks.filter((c) => c.status === "ok").length;

  return (
    <div>
      <div className="card">
        <h2>Load the planning files</h2>
        <p className="lead">Select the 8 CSV files for this planning period. We check each one before you continue.</p>
        <div className="actions">
          <label className="filedrop">
            <input type="file" multiple accept=".csv" onChange={(e) => pick(Array.from(e.target.files ?? []))} />
            <span>{busy ? "Reading files..." : "Choose the 8 CSV files"}</span>
          </label>
          <button onClick={useSample}>Use the sample files instead</button>
        </div>

        <ul className="filelist">
          {REQUIRED_FILES.map((f) => {
            const c = checks.find((x) => x.name === f.name);
            const st = c?.status ?? "todo";
            return (
              <li key={f.name} className={st}>
                <span className="tick">{st === "ok" ? "OK" : st === "bad" ? "FIX" : st === "missing" ? "MISSING" : "-"}</span>
                <span className="fname">{f.name}</span>
                <span className="fdetail">{c?.detail ?? ""}</span>
              </li>
            );
          })}
        </ul>
        {checks.length > 0 && okCount < 8 && (
          <p className="warn">{8 - okCount} file(s) still need attention. Fix them and choose the files again.</p>
        )}
      </div>

      {s && (
        <div className="card">
          <h2>What is in these files</h2>
          <div className="tiles">
            <div className="tile"><b>Planning period</b><span>{s.weeks} weeks</span><small>{s.horizonStart} to {s.horizonEnd}</small></div>
            <div className="tile"><b>Network</b><span>{s.stations} stations</span><small>{s.lines} lines, {s.hubs} interchange hubs, {s.tunnels} tunnels</small></div>
            <div className="tile"><b>Bookable spots</b><span>{s.spots}</span><small>tunnels and platforms, per direction</small></div>
            <div className="tile"><b>Contracts</b><span>{s.contracts}</span><small>{s.priority1} are Priority 1</small></div>
            <div className="tile"><b>Jobs to schedule</b><span>{s.jobs}</span><small>{s.nightsNeeded} work-nights needed in total</small></div>
            <div className="tile"><b>Access-nights available</b><span>{s.nightsPerWeek} / week</span><small>{s.nightsAvailable} across the whole period</small></div>
          </div>
          <p className="hint">
            An access-night is one night of track time at one spot, between the last train and the first. Every spot has a weekly limit; these numbers add those limits up.
          </p>
        </div>
      )}

      <div className="stepnav">
        <span />
        <button className="primary" disabled={!instance} onClick={onNext}>Next: choose rules</button>
      </div>
    </div>
  );
}
