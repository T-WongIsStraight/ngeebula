# Deploying the Track Access Scheduler

The judge-facing app is a Streamlit app. It runs the solver in the same process,
so there is no separate backend to host: one deploy gives you the whole thing.

- **Entry point:** `streamlit_app.py` (repo root)
- **Screens:** load the 8 planning CSVs → choose the rulebook (A / B / C) → read
  the schedule and download the 3 output CSVs
- **Solver:** `app/pipeline.py`, the same code path the FastAPI backend
  (`app/main.py`) uses, so both front doors give the same answer

---

## Run it locally

```bash
py -m streamlit run streamlit_app.py
```

It opens on <http://localhost:8501>. On the first screen press
**Load the official PS1 sample instance** to fill in all 8 files from
`frontend/public/sample/` — no uploading needed for a quick check.

To pick a different port, or to run it without opening a browser:

```bash
py -m streamlit run streamlit_app.py --server.headless true --server.port 8601
```

Install the dependencies first if you have not:

```bash
py -m pip install -r requirements.txt
```

---

## Deploy to Streamlit Community Cloud (free)

1. Push this repo to **GitHub**, on a **public** repository. Community Cloud's
   free tier only serves public repos.
2. Go to <https://share.streamlit.io> and sign in with the GitHub account that
   owns the repo. Authorise Streamlit when GitHub asks.
3. Press **Create app**, then **Deploy a public app from GitHub**.
4. Fill in the form:
   - **Repository:** `<your-org>/<your-repo>`
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
   - **App URL:** whatever subdomain you want the judges to visit
5. Open **Advanced settings** and set **Python version** to **3.12** or **3.13**.
   Leave *Secrets* empty — this app needs none.
6. Press **Deploy**. The first build installs `requirements.txt` (OR-Tools is the
   big one) and takes a few minutes. After that, every push to `main` redeploys
   automatically.

`.streamlit/config.toml` is committed, so the deployed app picks up the dark
theme and `server.headless = true` on its own. Nothing else needs configuring.

### Switching light / dark

The app ships **dark by default**, matching the control-room look of the React
frontend. Any viewer can switch to light from Streamlit's own **Settings** menu —
the **⋮** button in the top-right corner → *Settings* → *Appearance*. That choice
is per-viewer and does not change the deployed app for anyone else.

---

## What to expect on Community Cloud

**Resource limits.** A free app gets about **1 GB of RAM** and roughly **1 CPU**.
The solver is pinned to `num_workers=1` for exactly this reason (it also keeps the
output deterministic — see CLAUDE.md §12). Do not raise it.

**It sleeps.** An app with no visitors for about **12 hours** is put to sleep.
The next visitor wakes it, which takes 30–60 seconds and shows a "waking up"
screen. **Open the app yourself shortly before a demo or judging slot** so the
judges never land on a cold start.

**One CPU is shared.** If two people press *Build the schedule* at the same time,
both solves share the same core and both take longer. For a judging session,
one person driving is best.

### Expected solve times

Measured locally with `num_workers=1` on the public PS1 instance, at the default
60-second limit:

| Scenario | Local | On Community Cloud |
| --- | --- | --- |
| A · Track limits fixed | ~45 s | slower — expect up to the full limit |
| B · Deadlines fixed | ~55 s | slower — expect up to the full limit |
| C · Balanced | ~65 s | slower — expect up to the full limit |

Cloud hardware is slower than a laptop, so treat the local numbers as a floor.
The time limit on the rules screen is a **budget, not a promise**: the solver
stops early when it can prove the answer cannot be beaten, and stops at the limit
otherwise. If a run comes back with the **out of time** screen, raise the limit
(up to 300 seconds) and run it again.

---

## The FastAPI backend

`app/main.py` is still there and still works — it is the API contract in
CLAUDE.md §8.2, and it calls the same `app/pipeline.py`. Host it separately only
if you need the HTTP API (for the React frontend, or for a scripted run):

```bash
py -m uvicorn app.main:app --port 8000
```

The Streamlit app does **not** need it running.
