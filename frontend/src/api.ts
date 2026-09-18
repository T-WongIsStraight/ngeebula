// The only place that talks to the backend (CLAUDE.md §8). Nothing here
// computes a score, a violation or a schedule: it moves JSON around.

import type { Job, Scenario } from "./types";

/** "" means "same origin as this page" (the dev server proxies /api). */
const BASE: string = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

/** Every failure the UI can show, with the backend's own error_code when there is one. */
export class ApiError extends Error {
  readonly errorCode: string;
  readonly httpStatus: number;

  constructor(errorCode: string, message: string, httpStatus = 0) {
    super(message);
    this.name = "ApiError";
    this.errorCode = errorCode;
    this.httpStatus = httpStatus;
  }
}

function url(path: string): string {
  return `${BASE}${path}`;
}

/** Turn any non-2xx into an ApiError carrying the backend's error_code + message. */
async function unwrap(res: Response): Promise<unknown> {
  if (res.ok) {
    try {
      return await res.json();
    } catch {
      throw new ApiError("BAD_RESPONSE", "The server replied with something that is not JSON.", res.status);
    }
  }
  let code = `HTTP_${res.status}`;
  let message = `The server refused the request (HTTP ${res.status}).`;
  try {
    const body = (await res.json()) as { error_code?: string; message?: string; detail?: unknown };
    if (typeof body.error_code === "string") code = body.error_code;
    if (typeof body.message === "string") message = body.message;
    else if (typeof body.detail === "string") message = body.detail;
  } catch {
    /* no JSON body: keep the generic message */
  }
  throw new ApiError(code, message, res.status);
}

/** fetch() that never throws a raw TypeError: a dead network becomes error_code NETWORK. */
async function request(path: string, init?: RequestInit): Promise<unknown> {
  let res: Response;
  try {
    res = await fetch(url(path), init);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(
      "NETWORK",
      "Could not reach the scheduling server. Check that it is running and that the address is right.",
    );
  }
  return unwrap(res);
}

export async function health(): Promise<{ ok: boolean; version?: string; jobs_running?: number }> {
  return (await request("/api/health")) as { ok: boolean; version?: string; jobs_running?: number };
}

/**
 * Start a solve. The backend identifies each CSV by its own file name, so the
 * form field name does not matter; we send them all as "files".
 */
export async function solve(files: File[], scenario: Scenario, timeLimit: number): Promise<{ job_id: string }> {
  const body = new FormData();
  for (const f of files) body.append("files", f, f.name);
  body.append("scenario", scenario);
  body.append("time_limit", String(timeLimit));
  return (await request("/api/solve", { method: "POST", body })) as { job_id: string };
}

export async function getJob(jobId: string, signal?: AbortSignal): Promise<Job> {
  return (await request(`/api/jobs/${encodeURIComponent(jobId)}`, { signal })) as Job;
}

const POLL_MS = 2000;

/**
 * Ask for the job every 2 s until it stops running. Resolves with the finished
 * job (whatever its status). Aborting the signal rejects with an AbortError;
 * the solve itself keeps running on the server.
 */
export async function pollJob(jobId: string, onTick: (job: Job) => void, signal?: AbortSignal): Promise<Job> {
  for (;;) {
    if (signal?.aborted) throw new DOMException("Polling cancelled", "AbortError");
    const job = await getJob(jobId, signal);
    onTick(job);
    if (job.status !== "running") return job;
    await sleep(POLL_MS, signal);
  }
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Polling cancelled", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/** Direct link for a generated CSV, e.g. downloadUrl(id, "RESULTS.csv"). */
export function downloadUrl(jobId: string, filename: string): string {
  return url(`/api/jobs/${encodeURIComponent(jobId)}/download/${encodeURIComponent(filename)}`);
}
