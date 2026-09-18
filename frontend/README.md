# Track Access Scheduler — web app

The judge-facing front end for NebulaX PS1. A works controller (or a judge)
drops in the 8 instance CSVs, picks a rulebook (Scenario A, B or C), and gets
back a checked schedule: a verdict, a score with its breakdown, who finishes
late, two grids (jobs by week, track spots by week), a plain-English reason for
every job, and the 3 submission CSVs to download.

React 19 + TypeScript + Vite, plain CSS, no UI framework, no router, no chart
library.

**It never decides anything itself.** Every number on screen — feasible or not,
score, late days, extra nights, ECLO nights — comes from the backend's own
validator report (`app/validator.py`, CLAUDE.md §8.2). The only checks done in
the browser are: the 8 uploaded files have the official names, their header rows
carry the expected columns (CLAUDE.md §4), and a row-count summary of what you
loaded. There is no bundled schedule and no demo mode.

## Run it locally

You need the backend running first (from the repo root):

```powershell
.\run.ps1              # FastAPI on http://localhost:8000
```

Then:

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

`npm run dev` proxies every `/api/...` call to `http://localhost:8000`. Point it
somewhere else with `VITE_DEV_API`:

```bash
VITE_DEV_API=http://127.0.0.1:8040 npm run dev
```

The **"Load the official PS1 sample instance"** button on step 1 fetches the 8
CSVs in `public/sample/` and submits them exactly as if you had dragged them in,
so the sample path exercises the same code as a judge's upload.

## Environment variables

Copy `.env.example` to `.env.local` for local overrides.

| Variable | When | Meaning |
| --- | --- | --- |
| `VITE_DEV_API` | dev only | Where `npm run dev` forwards `/api` requests. Default `http://localhost:8000`. |
| `VITE_API_BASE_URL` | build time | Base URL of the hosted backend, no trailing slash. Empty (default) means "same origin as the page". |

## Build

```bash
npm run build          # tsc -b && vite build  ->  dist/
npm run preview        # serve dist/ locally
npm run lint           # oxlint
```

A production build with an empty `VITE_API_BASE_URL` expects the API on the same
origin. When the API lives elsewhere (the usual case), set the variable at build
time.

## Deploy to Netlify

`netlify.toml` at the repo root already points Netlify at this folder:

```toml
[build]
  base = "frontend"
  command = "npm run build"
  publish = "dist"
```

1. In Netlify, create a site from the repo (no extra build settings needed).
2. Add the environment variable **`VITE_API_BASE_URL`** = the public URL of the
   FastAPI backend, e.g. `https://ngeebula-api.onrender.com` (no trailing
   slash), then deploy. The variable is baked in at build time, so changing it
   needs a redeploy.
3. The backend must allow the Netlify origin through CORS and keep `JOBS_DIR`
   writable, otherwise downloads and polling fail.

Drag-and-drop deploys work too: `npm run build` and drop `frontend/dist` on
Netlify — but build it with `VITE_API_BASE_URL` set, or the app will look for
the API on the Netlify domain.

## Layout

```
src/
  api.ts             the only file that talks to the backend (solve, poll, download URLs)
  types.ts           mirror of the backend contract (CLAUDE.md §8.2)
  App.tsx            the 3-step flow: upload -> rules -> result, plus running and failure screens
  steps/             Step1Upload, Step2Rules, Running, Failed, ResultScreen, StepTrain, ThemeToggle
  views/             Timeline, Heatmap, ExplainPanel (the two grids and the explain panel)
  lib/               dates, csvHeader, instanceFiles, summary — pure helpers, no scoring
  index.css          the whole theme: custom properties on :root (light) and [data-theme="dark"]
public/sample/       the 8 official PS1 instance CSVs behind the sample button
```

Failure has its own screen for each backend status: `infeasible`, `timeout` and
`error` each show the server's message and what to do next.
