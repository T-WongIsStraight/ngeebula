"""'Jobs by week' — one column per week, one row per contract (folded) or job.

A filled square = one night of work that week. Everything shown is read from the
backend payload: nights from ``schedule_access``, lateness from ``results``,
deadlines from each contract's ``planned_completion_date``. Nothing is scored,
validated or re-scheduled here.

Plotly cannot fold rows on its own, so the fold lives in a ``st.multiselect``
above the chart: contracts are folded by default and the picker opens the ones
the controller wants to look at.
"""

from __future__ import annotations

from typing import Any, Mapping

import plotly.graph_objects as go
import streamlit as st

from .grid_helpers import (
    DEADLINE_COLOR,
    WAITING_COLOR,
    activity_week_key,
    build_index,
    fmt_date,
    fmt_day_month,
    late_label,
    num,
    priority_color,
    rows,
    sorted_contracts,
    text,
    unique_labels,
    week_end,
    week_of_date,
    week_range_label,
    week_start,
)

_ROW_PX = 26
_CHROME_PX = 110
_LATE_BAR = "rgba(193,63,78,0.28)"
_OK_BAR = "rgba(136,142,150,0.26)"


def _body_color() -> str:
    """Text colour for marks Plotly's Streamlit template does not reach."""
    try:
        return "#E6EDF3" if st.context.theme.type == "dark" else "#1F2328"
    except Exception:  # pragma: no cover - older hosts without st.context.theme
        return "#6B7280"


def _emit(key: str, activity_id: str | None) -> str | None:
    """Only report a click when it is a NEW click.

    Plotly selection state survives reruns, so without this the chart would keep
    re-announcing the same job and fight the heat-map for the explain panel.
    """
    slot = f"{key}__last_click"
    if st.session_state.get(slot) == activity_id:
        return None
    st.session_state[slot] = activity_id
    return activity_id


def render_gantt(
    result: Mapping[str, Any], weeks: list[int], selected: str | None, key: str
) -> str | None:
    """Draw the week grid. Returns an activity_id when a job marker is clicked."""
    idx = build_index(result)
    horizon = idx.horizon_start
    contracts = sorted_contracts(rows(result.get("instance", {}), "contracts"))

    if not contracts or not weeks:
        st.info("No contracts to show for this week range.")
        return None

    numbers = [text(c.get("contract_number")) for c in contracts]
    show_all = st.checkbox(
        "Show the jobs inside every contract",
        key=f"{key}__all",
        help="Off means one row per contract: the shape of the whole programme on one screen.",
    )
    picked = st.multiselect(
        "Show jobs for",
        options=numbers,
        default=[],
        key=f"{key}__open",
        placeholder="Pick a contract to open its jobs",
        disabled=show_all,
        help="Opens a row per job underneath the contract, one marker per night worked.",
    )
    open_contracts = set(numbers) if show_all else set(picked)

    # ---------------------------------------------------------- build rows
    # Rows are collected top-down, then handed to Plotly bottom-up.
    labels: list[str] = []
    kinds: list[str] = []  # "contract" | "job"
    payload: list[dict[str, Any]] = []

    for contract in contracts:
        number = text(contract.get("contract_number"))
        priority = num(contract.get("contract_priority"))
        jobs = idx.activities_by_contract.get(number, [])
        late_days, late_text = late_label(idx.result_by_contract.get(number))
        labels.append(f"P{priority or '?'}  {number}  ({len(jobs)})")
        kinds.append("contract")
        payload.append(
            {
                "number": number,
                "priority": priority,
                "late_text": late_text,
                "late_days": late_days,
                "deadline_week": week_of_date(horizon, contract.get("planned_completion_date")),
                "deadline_date": text(contract.get("planned_completion_date")),
                "span": idx.span_by_contract.get(number),
                "description": text(contract.get("contract_description")),
            }
        )
        if number in open_contracts:
            for job in jobs:
                activity_id = text(job.get("activity_id"))
                nights = num(job.get("total_accesses"))
                labels.append(f"    {activity_id}  ({nights}n)")
                kinds.append("job")
                payload.append(
                    {
                        "activity_id": activity_id,
                        "priority": priority,
                        "total": nights,
                        "span": idx.span_by_activity.get(activity_id),
                    }
                )

    labels = unique_labels(labels)
    y_order = list(reversed(labels))  # Plotly draws categories bottom-up.

    # --------------------------------------------------------- the figure
    fig = go.Figure()
    lo, hi = min(weeks), max(weeks)

    # 1. Contract span bars: first worked week to last worked week.
    bar_y, bar_base, bar_width, bar_color, bar_text, bar_hover = [], [], [], [], [], []
    for label, kind, row in zip(labels, kinds, payload):
        if kind != "contract" or not row["span"]:
            continue
        start, end = row["span"]
        left, right = max(start, lo - 1), min(end, hi + 1)
        if right < lo or left > hi:
            continue
        bar_y.append(label)
        bar_base.append(left - 0.42)
        bar_width.append((right - left) + 0.84)
        bar_color.append(_LATE_BAR if row["late_days"] > 0 else _OK_BAR)
        bar_text.append(row["late_text"])
        bar_hover.append(
            f"<b>{row['number']}</b>"
            + (f" · {row['description']}" if row["description"] else "")
            + f"<br>Priority {row['priority']} · {row['late_text']}"
            + f"<br>Works from {week_range_label(horizon, start)}"
            + f"<br>through {week_range_label(horizon, end)}"
        )
    if bar_y:
        fig.add_trace(
            go.Bar(
                x=bar_width,
                y=bar_y,
                base=bar_base,
                orientation="h",
                marker=dict(color=bar_color, line=dict(width=0)),
                text=bar_text,
                textposition="auto",
                insidetextanchor="start",
                textfont=dict(size=11, color=_body_color()),
                cliponaxis=False,
                hovertext=bar_hover,
                hovertemplate="%{hovertext}<extra></extra>",
                showlegend=False,
                width=0.55,
            )
        )

    # 2. Deadline diamonds, one per contract, at the week of planned_completion_date.
    dl_x, dl_y, dl_hover = [], [], []
    for label, kind, row in zip(labels, kinds, payload):
        if kind != "contract":
            continue
        dweek = row["deadline_week"]
        if dweek is None or not (lo <= dweek <= hi):
            continue
        dl_x.append(dweek)
        dl_y.append(label)
        dl_hover.append(
            f"<b>{row['number']} deadline</b><br>{row['deadline_date']}"
            f"<br>week {dweek}, ending {fmt_date(week_end(horizon, dweek))}"
            f"<br>Outcome: {row['late_text']}"
        )
    if dl_x:
        fig.add_trace(
            go.Scatter(
                x=dl_x,
                y=dl_y,
                mode="markers",
                marker=dict(
                    symbol="diamond-tall",
                    size=15,
                    color=DEADLINE_COLOR,
                    line=dict(width=1, color="rgba(255,255,255,0.65)"),
                ),
                hovertext=dl_hover,
                hovertemplate="%{hovertext}<extra></extra>",
                showlegend=False,
            )
        )

    # 3. Waiting weeks: hollow markers between a job's first and last night.
    wait_x, wait_y, wait_hover = [], [], []
    # 4. Worked nights, one trace per priority so colours stay meaningful.
    by_priority: dict[int, dict[str, list[Any]]] = {}

    for label, kind, row in zip(labels, kinds, payload):
        if kind != "job":
            continue
        activity_id = row["activity_id"]
        span = row["span"]
        for week in weeks:
            night = idx.access_by_activity_week.get(activity_week_key(activity_id, week))
            if night is None:
                if span and span[0] < week < span[1]:
                    wait_x.append(week)
                    wait_y.append(label)
                    wait_hover.append(
                        f"<b>{activity_id}</b> is waiting in {week_range_label(horizon, week)}"
                        "<br>it works before and after, but not this week"
                    )
                continue
            eclo = num(night.get("eclo")) == 1
            bucket = by_priority.setdefault(
                row["priority"], {"x": [], "y": [], "t": [], "cd": [], "h": []}
            )
            bucket["x"].append(week)
            bucket["y"].append(label)
            bucket["t"].append("E" if eclo else "")
            bucket["cd"].append(activity_id)
            bucket["h"].append(
                f"<b>{activity_id}</b> works {week_range_label(horizon, week)}"
                f"<br>Night slot {num(night.get('access_night'))}"
                " of the contract's weekly allowance"
                f"<br>Night {num(night.get('access_seq'))} of {row['total']}"
                + ("<br>ECLO: a longer night (counts 1.5)" if eclo else "")
                + "<br><i>click to see why it sits here</i>"
            )

    if wait_x:
        fig.add_trace(
            go.Scatter(
                x=wait_x,
                y=wait_y,
                mode="markers",
                marker=dict(
                    symbol="circle",
                    size=9,
                    color="rgba(0,0,0,0)",
                    line=dict(width=1.4, color=WAITING_COLOR),
                ),
                hovertext=wait_hover,
                hovertemplate="%{hovertext}<extra></extra>",
                showlegend=False,
            )
        )

    for priority in sorted(by_priority):
        bucket = by_priority[priority]
        fig.add_trace(
            go.Scatter(
                x=bucket["x"],
                y=bucket["y"],
                mode="markers+text",
                marker=dict(
                    symbol="square",
                    size=15,
                    color=priority_color(priority),
                    line=dict(width=0.8, color="rgba(255,255,255,0.55)"),
                ),
                # Picking one night must not grey out the rest of the programme.
                unselected=dict(marker=dict(opacity=1)),
                text=bucket["t"],
                textposition="middle center",
                textfont=dict(size=9, color="#FFFFFF"),
                customdata=bucket["cd"],
                hovertext=bucket["h"],
                hovertemplate="%{hovertext}<extra></extra>",
                showlegend=False,
            )
        )

    # 5. A ring around whatever the rest of the app currently has open.
    if selected:
        sel_x = [
            week
            for week in weeks
            if activity_week_key(selected, week) in idx.access_by_activity_week
        ]
        sel_label = next(
            (
                label
                for label, kind, row in zip(labels, kinds, payload)
                if kind == "job" and row["activity_id"] == selected
            ),
            None,
        )
        if sel_x and sel_label:
            fig.add_trace(
                go.Scatter(
                    x=sel_x,
                    y=[sel_label] * len(sel_x),
                    mode="markers",
                    marker=dict(
                        symbol="square-open",
                        size=24,
                        color=DEADLINE_COLOR,
                        line=dict(width=2.2, color=DEADLINE_COLOR),
                    ),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

    fig.update_layout(
        barmode="overlay",
        bargap=0.45,
        margin=dict(l=8, r=16, t=8, b=8),
        height=max(260, _CHROME_PX + _ROW_PX * len(labels)),
        hovermode="closest",
        dragmode=False,
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(
        range=[lo - 0.6, hi + 0.6],
        tickmode="array",
        tickvals=weeks,
        ticktext=[f"{w}<br>{fmt_day_month(week_start(horizon, w))}" for w in weeks],
        side="top",
        showgrid=True,
        gridcolor="rgba(136,142,150,0.18)",
        zeroline=False,
        fixedrange=True,
        title=None,
    )
    fig.update_yaxes(
        type="category",
        categoryorder="array",
        categoryarray=y_order,
        showgrid=False,
        zeroline=False,
        fixedrange=True,
        title=None,
        automargin=True,
    )

    event = st.plotly_chart(
        fig,
        theme="streamlit",
        on_select="rerun",
        selection_mode="points",
        key=key,
        config={"displayModeBar": False, "scrollZoom": False},
    )

    st.caption(
        "Each square is one night of work. "
        ":red[■] priority 1 · :orange[■] priority 2 · :blue[■] priority 3 "
        "· **E** inside a square = ECLO, a longer night "
        "· ○ waiting (works before and after, not that week) "
        "· :violet[◆] deadline week. "
        "The bar on a contract row runs from its first working week to its last, "
        "and carries its lateness. Click a square to see why that job sits there."
    )

    return _emit(key, _clicked_activity(event, idx.activity_by_id))


def _clicked_activity(event: Any, known: Mapping[str, Any]) -> str | None:
    """Pull the activity_id out of a Plotly selection event, if there is one."""
    try:
        points = event.selection["points"]
    except Exception:
        return None
    for point in points or []:
        data = point.get("customdata") if isinstance(point, Mapping) else None
        if isinstance(data, (list, tuple)) and data:
            candidate = text(data[0])
        elif isinstance(data, str):
            candidate = data
        else:
            continue
        if candidate in known:
            return candidate
    return None
