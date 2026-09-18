"""STEP 1: load the 8 planning files.

We check two things here and nothing else: is the file one of the 8 official
names, and does its header row carry the columns the scheduler needs. The
scheduler reads the contents itself. The summary below the checklist is plain
row counting — it decides nothing.
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from ui import state
from ui.state import (
    INSTANCE_FILES,
    SAMPLE_DIR,
    WHAT_IS_IT,
)


def _accept(incoming: List[Any]) -> None:
    """Merge newly chosen files into what we already hold, then re-check."""
    files: Dict[str, bytes] = dict(st.session_state["files"])
    bad: Dict[str, str] = dict(st.session_state["bad_headers"])
    extras: List[str] = []

    for uploaded in incoming:
        name = state.canonical_name(uploaded.name)
        if name not in INSTANCE_FILES:
            extras.append(str(uploaded.name).replace("\\", "/").split("/")[-1])
            continue
        blob = uploaded.getvalue()
        missing = state.missing_columns(name, blob)
        if missing:
            files.pop(name, None)
            bad[name] = "header is missing: " + ", ".join(missing)
        else:
            files[name] = blob
            bad.pop(name, None)

    st.session_state["files"] = files
    st.session_state["bad_headers"] = bad
    st.session_state["extras"] = extras


def _load_sample() -> None:
    """Read the 8 official PS1 sample CSVs bundled in the repo."""
    try:
        files = {name: (SAMPLE_DIR / name).read_bytes() for name in INSTANCE_FILES}
    except OSError as exc:
        st.session_state["problem"] = (
            f"Could not read the bundled sample instance: {exc}. "
            f"It should be in {SAMPLE_DIR}."
        )
        return
    state.clear_files()
    st.session_state["files"] = files


def _summary(files: Dict[str, bytes]) -> Dict[str, Any]:
    """What is in these files, by counting rows. No scheduling, no scoring."""
    rows = {name: state.read_rows(blob) for name, blob in files.items()}

    parameters = {
        r.get("key", "").strip().lower(): r.get("value", "").strip()
        for r in rows.get("06_PARAMETERS.csv", [])
    }
    horizon_start = parameters.get("horizon_start", "")
    horizon_weeks = int(state.as_number(parameters.get("horizon_weeks", 0)))

    stations = rows.get("02_STATIONS.csv", [])
    contracts = rows.get("07_PROJECT_DETAILS.csv", [])
    activities = rows.get("08_ACTIVITY_DETAILS.csv", [])

    return {
        "horizon_start": horizon_start,
        "horizon_end": state.week_end(horizon_start, horizon_weeks) if horizon_weeks else "",
        "horizon_weeks": horizon_weeks,
        "lines": len(rows.get("01_LINES.csv", [])),
        "stations": len(stations),
        "hubs": sum(1 for r in stations if r.get("is_interchange", "") == "1"),
        "sectors": len(rows.get("03_SECTORS.csv", [])),
        "spots": len(rows.get("04_LOCATION_SUPPLY.csv", [])),
        "contracts": len(contracts),
        "priority1": sum(1 for r in contracts if r.get("contract_priority", "") == "1"),
        "jobs": len(activities),
        "nights": int(sum(state.as_number(r.get("total_accesses", 0)) for r in activities)),
    }


def render() -> None:
    files: Dict[str, bytes] = st.session_state["files"]
    bad: Dict[str, str] = st.session_state["bad_headers"]

    st.subheader("Load the planning files")
    st.write(
        "Drop in the 8 CSV files for this planning period. We check the file names "
        "and header rows here; the scheduler reads the contents itself."
    )

    with st.container(border=True):
        chosen = st.file_uploader(
            "The 8 planning CSV files",
            type="csv",
            accept_multiple_files=True,
            key=f"uploader_{st.session_state['uploader_nonce']}",
            help="Choose all 8 at once, or a few at a time. A file you load again replaces the earlier one.",
        )
        if chosen:
            _accept(chosen)
            files = st.session_state["files"]
            bad = st.session_state["bad_headers"]

        with st.container(horizontal=True):
            if st.button(
                "Load the official PS1 sample instance",
                icon=":material/download:",
                type="primary" if not files else "secondary",
            ):
                _load_sample()
                st.rerun()
            if files or bad:
                if st.button("Clear files", icon=":material/close:"):
                    state.clear_files()
                    st.rerun()

    # ---- the checklist, one row per official file ----
    ok_count = 0
    for name in INSTANCE_FILES:
        if name in files:
            ok_count += 1
            mark, detail = ":green-badge[OK]", f"{max(1, round(len(files[name]) / 1024))} KB · {WHAT_IS_IT[name]}"
        elif name in bad:
            mark, detail = ":red-badge[FIX]", bad[name]
        else:
            mark, detail = ":gray-badge[MISSING]", "not chosen yet"
        st.markdown(f"{mark} &nbsp; `{name}` &nbsp; :gray[{detail}]")

    st.space("small")
    if ok_count == 8:
        st.success("8 of 8 files ready.", icon=":material/check_circle:")
    else:
        st.info(
            f"{ok_count} of 8 files ready. Every file must be present with its official name.",
            icon=":material/info:",
        )

    extras = st.session_state["extras"]
    if extras:
        shown = ", ".join(extras[:6]) + ("…" if len(extras) > 6 else "")
        st.warning(
            f"Ignored {len(extras)} file{'' if len(extras) == 1 else 's'} that "
            f"{'is' if len(extras) == 1 else 'are'} not one of the 8: {shown}",
            icon=":material/warning:",
        )
    if st.session_state["problem"]:
        st.error(st.session_state["problem"], icon=":material/error:")

    # ---- what is in these files ----
    if ok_count == 8:
        summary = _summary(files)
        st.space("medium")
        st.subheader("What is in these files")

        top = st.columns(3)
        top[0].metric(
            "Planning period",
            f"{summary['horizon_weeks']} weeks",
            help="From 06_PARAMETERS.csv.",
            border=True,
        )
        top[0].caption(
            f"{state.format_date(summary['horizon_start'])} to {state.format_date(summary['horizon_end'])}"
        )
        top[1].metric("Lines", summary["lines"], border=True)
        top[1].caption(f"{summary['sectors']} tunnels between stations")
        top[2].metric("Stations", summary["stations"], border=True)
        top[2].caption(f"{summary['hubs']} interchange hubs")

        bottom = st.columns(3)
        bottom[0].metric("Bookable spots", summary["spots"], border=True)
        bottom[0].caption("tunnels and platforms, per direction")
        bottom[1].metric("Contracts", summary["contracts"], border=True)
        bottom[1].caption(f"{summary['priority1']} are Priority 1")
        bottom[2].metric("Jobs to schedule", summary["jobs"], border=True)
        bottom[2].caption(f"{summary['nights']} work-nights needed in total")

        st.caption(
            "A work-night is one night of track time at one spot, between the last train "
            "and the first. Counts come straight from the files you loaded."
        )

    # ---- next ----
    st.space("medium")
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button(
            "Next: choose rules",
            type="primary",
            disabled=ok_count < 8,
            icon=":material/arrow_forward:",
        ):
            state.go("rules")
