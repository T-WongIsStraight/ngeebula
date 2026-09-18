"""Running the scheduler, and the three screens for when it does not finish.

The 8 files the controller loaded are written to a throwaway folder, the
pipeline runs against it, the 3 output CSVs are read back into memory for the
download buttons, and the folder is deleted. Nothing is cached between runs and
nothing is shared between viewers.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import streamlit as st

from app.pipeline import run_pipeline
from ui import state
from ui.state import INSTANCE_FILES, SUBMISSION_FILES


def render_running() -> None:
    """Do the solve, keep the result, then move to the screen that fits it."""
    scenario = st.session_state["scenario"]
    time_limit = int(st.session_state["time_limit"])
    files = st.session_state["files"]

    if len(files) != len(INSTANCE_FILES):
        st.session_state["problem"] = "Some files went missing. Load all 8 again."
        state.go("upload")
        return

    folder = Path(tempfile.mkdtemp(prefix="trackaccess_"))
    try:
        for name, blob in files.items():
            (folder / name).write_bytes(blob)

        with st.status(
            f"Building the schedule for Scenario {scenario}…", expanded=True
        ) as status:
            st.write("Placing every job across the whole planning period…")
            outcome = run_pipeline(
                folder,
                scenario,
                time_limit_seconds=float(time_limit),
                num_workers=1,  # deterministic output; see CLAUDE.md §12
                out_dir=folder,
                label=f"streamlit scenario {scenario}",
            )
            st.write("Checking every safety rule, buffer and weekly limit…")
            st.write("Scoring the result against the scenario's price list…")
            elapsed = float(outcome.get("elapsed_s") or 0.0)
            st.write(f"Finished in {elapsed:.1f} seconds.")
            status.update(
                label=f"Scenario {scenario} finished in {elapsed:.1f} s",
                state="complete" if outcome["status"] == "done" else "error",
                expanded=False,
            )

        st.session_state["job"] = outcome
        st.session_state["selected_activity"] = None
        st.session_state["csvs"] = (
            {
                name: (folder / name).read_bytes()
                for name in SUBMISSION_FILES
                if (folder / name).exists()
            }
            if outcome["status"] == "done"
            else {}
        )
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    state.go("result" if outcome["status"] == "done" else "failed")


def render_failed() -> None:
    """One screen per reason, each with the server's own message and a next step."""
    job = st.session_state["job"] or {}
    kind = job.get("status", "error")
    message = job.get("message") or "No message was returned."
    error_code = job.get("error_code")
    scenario = st.session_state["scenario"]
    time_limit = int(st.session_state["time_limit"])

    if kind == "infeasible":
        st.error("NO SCHEDULE — no schedule fits these rules.", icon=":material/block:")
        next_steps = [
            f"Scenario {scenario} forbids the escape routes the scheduler needed. "
            "Scenario C allows one extra night per spot and longer nights; Scenario B "
            "allows as many extra nights as it takes.",
            "Check 08_ACTIVITY_DETAILS.csv: a job whose planned start date leaves fewer "
            "weeks than it needs nights can never fit, because a job works at most one "
            "night a week.",
            "Check that every location used by a job appears in 04_LOCATION_SUPPLY.csv "
            "with a capacity above zero.",
        ]
    elif kind == "timeout":
        st.warning("OUT OF TIME — the scheduler ran out of time.", icon=":material/timer_off:")
        next_steps = [
            f"The scheduler had {time_limit} seconds and had not found a schedule it could "
            "prove legal. Raise the time limit (up to 300 seconds) and run it again.",
            "Larger instances need more time. If 300 seconds is not enough, try Scenario B "
            "or C, which give the scheduler more room to move.",
        ]
    else:
        st.error(
            "SOMETHING WENT WRONG — the scheduler could not finish.", icon=":material/error:"
        )
        next_steps = [
            "Run it again: the scheduler may have been interrupted.",
            "If it keeps happening, check that the 8 files are the ones the judges gave "
            "you, unedited, and that each one opens as a plain CSV.",
        ]

    with st.container(border=True):
        st.markdown("**What the scheduler said**")
        st.write(message)
        if error_code:
            st.caption(f"Error code: `{error_code}`")

        st.markdown("**What to do next**")
        for step in next_steps:
            st.markdown(f"- {step}")

    st.space("medium")
    with st.container(horizontal=True, horizontal_alignment="distribute"):
        if st.button(
            "Back: change rules and try again",
            type="primary",
            icon=":material/arrow_back:",
        ):
            state.go("rules")
        if st.button("Start over with new files", icon=":material/restart_alt:"):
            state.reset()
            state.go("upload")
