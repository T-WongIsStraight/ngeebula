// Taking in the 8 planning files: match them to the official names, check the
// header row, and read a summary. No scheduling, no scoring.

import { INSTANCE_FILES } from "../types";
import { canonicalName, checkHeader } from "./csvHeader";
import { summarise } from "./summary";
import type { InstanceSummary } from "./summary";

export type FileStatus = "ok" | "bad" | "missing";
export type FileCheck = { name: string; status: FileStatus; detail: string };

export type AcceptedFiles = {
  /** The accepted files keyed by their official name. */
  accepted: Record<string, File>;
  /** One row per official file, in order, for the checklist. */
  checks: FileCheck[];
  /** Filled in only when all 8 are present and their headers are right. */
  summary: InstanceSummary | null;
  /** Names that were dropped in but are not one of the 8. */
  extras: string[];
};

/**
 * Merge newly chosen files into what we already have, then re-check everything.
 * A second drop of the same name replaces the earlier file.
 */
export async function acceptFiles(existing: Record<string, File>, incoming: File[]): Promise<AcceptedFiles> {
  const accepted: Record<string, File> = { ...existing };
  const badHeaders: Record<string, string> = {};
  const extras: string[] = [];

  for (const file of incoming) {
    const name = canonicalName(file.name);
    if (!(INSTANCE_FILES as readonly string[]).includes(name)) {
      extras.push(file.name.split(/[\\/]/).pop() ?? file.name);
      continue;
    }
    const check = await checkHeader(file);
    if (check.ok) {
      accepted[name] = file;
      delete badHeaders[name];
    } else {
      delete accepted[name];
      badHeaders[name] =
        check.missingColumns.length > 0
          ? `header is missing: ${check.missingColumns.join(", ")}`
          : "the first line does not look like the expected header row";
    }
  }

  const checks: FileCheck[] = INSTANCE_FILES.map((name) => {
    const file = accepted[name];
    if (file) return { name, status: "ok", detail: `${Math.round(file.size / 1024)} KB` };
    if (badHeaders[name]) return { name, status: "bad", detail: badHeaders[name] };
    return { name, status: "missing", detail: "not chosen yet" };
  });

  const complete = checks.every((c) => c.status === "ok");
  const summary = complete ? await summarise(accepted) : null;
  return { accepted, checks, summary, extras };
}

/** Fetch the 8 official PS1 sample CSVs bundled in public/sample and hand them over as real uploads. */
export async function loadSampleFiles(): Promise<File[]> {
  const base = import.meta.env.BASE_URL || "/";
  return Promise.all(
    INSTANCE_FILES.map(async (name) => {
      const res = await fetch(`${base}sample/${name}`);
      if (!res.ok) throw new Error(`Could not read the bundled sample file ${name} (HTTP ${res.status}).`);
      const blob = await res.blob();
      return new File([blob], name, { type: "text/csv" });
    }),
  );
}

/** Pull every file out of a drop, walking into folders when the browser allows it. */
export async function filesFromDrop(dt: DataTransfer): Promise<File[]> {
  const items = Array.from(dt.items ?? []);
  const entries = items
    .map((item) => (typeof item.webkitGetAsEntry === "function" ? item.webkitGetAsEntry() : null))
    .filter((e): e is FileSystemEntry => e !== null);

  if (entries.length === 0) return Array.from(dt.files ?? []);

  const out: File[] = [];
  for (const entry of entries) await walk(entry, out);
  return out.length > 0 ? out : Array.from(dt.files ?? []);
}

async function walk(entry: FileSystemEntry, out: File[]): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File | null>((resolve) =>
      (entry as FileSystemFileEntry).file(resolve, () => resolve(null)),
    );
    if (file) out.push(file);
    return;
  }
  if (!entry.isDirectory) return;
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve) =>
      reader.readEntries(resolve, () => resolve([])),
    );
    if (batch.length === 0) return;
    for (const child of batch) await walk(child, out);
  }
}
