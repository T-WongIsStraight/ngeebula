"""Track Access Scheduler — the Streamlit front end.

This is the file Streamlit Community Cloud runs. It is a three-step wizard:
load the 8 planning files, choose the rulebook, read the schedule. The solving
happens in ``app.pipeline``, which is the same code path the FastAPI backend
uses, so both front doors produce exactly the same answer.

Run it locally with:  py -m streamlit run streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

from ui import results, rules, run, state, theme, upload

st.set_page_config(
    page_title="Track Access Scheduler",
    page_icon="🚆",
    layout="wide",
)

state.init()

theme.header()
theme.step_train(state.STEP_OF.get(st.session_state["phase"], 1))

phase = st.session_state["phase"]
if phase == "upload":
    upload.render()
elif phase == "rules":
    rules.render()
elif phase == "running":
    run.render_running()
elif phase == "failed":
    run.render_failed()
elif phase == "result":
    results.render()
else:  # pragma: no cover - defensive
    state.go("upload")
