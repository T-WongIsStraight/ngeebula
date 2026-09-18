// STEP 1: load the 8 planning files, check their names and header rows, and
// show what is inside them before anything is sent to the scheduler.

import { useRef, useState } from "react";
import { filesFromDrop } from "../lib/instanceFiles";
import type { FileCheck } from "../lib/instanceFiles";
import type { InstanceSummary } from "../lib/summary";
import { formatDate } from "../lib/dates";

const LABEL: Record<string, string> = {
  ok: "OK",
  bad: "FIX",
  missing: "MISSING",
};

const WHAT_IS_IT: Record<string, string> = {
  "01_LINES.csv": "the train lines",
  "02_STATIONS.csv": "stations in order, hubs flagged",
  "03_SECTORS.csv": "tunnels between stations",
  "04_LOCATION_SUPPLY.csv": "bookable spots and their weekly limit",
  "05_BUFFER_LOCATION.csv": "safety buffer per kind of work",
  "06_PARAMETERS.csv": "first week and how many weeks",
  "07_PROJECT_DETAILS.csv": "the contracts and their deadlines",
  "08_ACTIVITY_DETAILS.csv": "the jobs to schedule",
};

type Props = {
  checks: FileCheck[];
  summary: InstanceSummary | null;
  busy: boolean;
  problem: string | null;
  onFiles: (files: File[]) => void;
  onSample: () => void;
  onClear: () => void;
  onNext: () => void;
};

export function Step1Upload({ checks, summary, busy, problem, onFiles, onSample, onClear, onNext }: Props) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const okCount = checks.filter((c) => c.status === "ok").length;
  const ready = okCount === 8 && summary !== null;

  async function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setOver(false);
    onFiles(await filesFromDrop(e.dataTransfer));
  }

  return (
    <div>
      <div className="card">
        <h2>Load the planning files</h2>
        <p className="lead">
          Drop in the 8 CSV files for this planning period, or the folder that holds them. We check the file names and
          header rows here; the scheduler reads the contents itself.
        </p>

        <div
          className={"filedrop" + (over ? " over" : "")}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
        >
          <svg viewBox="0 0 48 32" width="56" height="38" aria-hidden="true">
            <rect x="1" y="6" width="46" height="20" rx="6" fill="none" stroke="var(--border)" strokeWidth="2" />
            <rect x="8" y="12" width="12" height="8" rx="2" fill="var(--accent)" opacity=".85" />
            <rect x="24" y="12" width="16" height="8" rx="2" fill="var(--border)" />
          </svg>
          <div>
            <b>Drop the 8 CSV files here</b>
            <p className="hint">or a folder containing them</p>
          </div>
          <div className="actions">
            <button type="button" className="primary" disabled={busy} onClick={() => input.current?.click()}>
              {busy ? "Reading files…" : "Choose files"}
            </button>
            <button type="button" disabled={busy} onClick={onSample}>
              Load the official PS1 sample instance
            </button>
          </div>
          <input
            ref={input}
            type="file"
            multiple
            accept=".csv,text/csv"
            hidden
            onChange={(e) => {
              onFiles(Array.from(e.target.files ?? []));
              e.target.value = "";
            }}
          />
        </div>

        <ul className="filelist">
          {checks.map((c) => (
            <li key={c.name} className={c.status}>
              <span className="tick">{LABEL[c.status]}</span>
              <span className="fname">{c.name}</span>
              <span className="fdetail">{c.status === "bad" ? c.detail : (WHAT_IS_IT[c.name] ?? c.detail)}</span>
            </li>
          ))}
        </ul>

        <div className="filefoot">
          <p className={okCount === 8 ? "ok-text" : "hint"}>
            {okCount} of 8 files ready{okCount < 8 ? ". Every file must be present with its official name." : "."}
          </p>
          {okCount > 0 && (
            <button type="button" onClick={onClear}>
              Clear files
            </button>
          )}
        </div>
        {problem && <p className="bad-text">{problem}</p>}
      </div>

      {summary && (
        <div className="card">
          <h2>What is in these files</h2>
          <div className="tiles">
            <div className="tile">
              <b>Planning period</b>
              <span>{summary.horizonWeeks} weeks</span>
              <small>
                {formatDate(summary.horizonStart)} to {formatDate(summary.horizonEnd)}
              </small>
            </div>
            <div className="tile">
              <b>Lines</b>
              <span>{summary.lines}</span>
              <small>{summary.sectors} tunnels between stations</small>
            </div>
            <div className="tile">
              <b>Stations</b>
              <span>{summary.stations}</span>
              <small>{summary.hubs} interchange hubs</small>
            </div>
            <div className="tile">
              <b>Bookable spots</b>
              <span>{summary.spots}</span>
              <small>tunnels and platforms, per direction</small>
            </div>
            <div className="tile">
              <b>Contracts</b>
              <span>{summary.contracts}</span>
              <small>{summary.priority1} are Priority 1</small>
            </div>
            <div className="tile">
              <b>Jobs to schedule</b>
              <span>{summary.jobs}</span>
              <small>{summary.nightsNeeded} work-nights needed in total</small>
            </div>
          </div>
          <p className="hint">
            A work-night is one night of track time at one spot, between the last train and the first. Counts come
            straight from the files you loaded.
          </p>
        </div>
      )}

      <div className="stepnav">
        <span />
        <button type="button" className="primary" disabled={!ready} onClick={onNext}>
          Next: choose rules
        </button>
      </div>
    </div>
  );
}
