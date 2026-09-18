"""The page heading and the step indicator.

The indicator is drawn like a train line: three stations, a line between them,
and the train sitting at the step you are on. It is built from native Streamlit
elements and Markdown colour directives, so it follows whichever theme the
viewer has chosen in Streamlit's own Settings menu.
"""

from __future__ import annotations

import streamlit as st

from ui.state import STEPS


def header() -> None:
    st.title("Track Access Scheduler")
    st.caption(
        "Plans which contractor works on which stretch of track, each week, "
        "without breaking a safety rule or a deadline more than it has to."
    )


def step_train(step: int) -> None:
    """Three stations on a line. `step` is 1, 2 or 3."""
    columns = st.columns(len(STEPS), gap="small")
    for index, label in enumerate(STEPS):
        number = index + 1
        with columns[index]:
            if number < step:
                st.markdown(":green[━━━━━━━━━━━━━━━━━━━━━━━]")
                st.markdown(f":green[**● Step {number}**] · :green[{label}]")
            elif number == step:
                st.markdown(":blue[━━━━━━━━━━━━━━━━━━━━━━━]")
                st.markdown(f":blue[**🚆 Step {number}**] · **{label}**")
            else:
                st.markdown(":gray[━━━━━━━━━━━━━━━━━━━━━━━]")
                st.markdown(f":gray[○ Step {number} · {label}]")
    st.space("small")
