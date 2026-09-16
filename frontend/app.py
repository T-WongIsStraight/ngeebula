from __future__ import annotations

import os
from datetime import timedelta
from html import escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import ApiClient, ApiClientError
from data_utils import (
    STATUS_COLORS,
    build_recommendation,
    detect_conflicts,
    load_demo_payload,
    normalise_schedule,
)


APP_DIR = Path(__file__).resolve().parent
DEFAULT_API_URL = os.getenv("NGEEBULA_API_URL", "http://127.0.0.1:8000")
LINE_META = {
    "NS": {"name": "North South", "color": "#FF4D5A", "class": "ns"},
    "EW": {"name": "East West", "color": "#29C77E", "class": "ew"},
    "CCL": {"name": "Circle", "color": "#F2A632", "class": "ccl"},
}

st.set_page_config(
    page_title="Ngeebula Rail Maintenance",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_styles() -> None:
    css = (APP_DIR / "styles.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def get_dashboard_data(api_url: str) -> tuple[list[dict], list[dict], list[dict], bool, str]:
    client = ApiClient(api_url)
    try:
        schedule = client.get_gantt_data()
        alerts = client.get_alerts()
        audit_logs = client.get_audit_logs()
        if not schedule:
            raise ApiClientError("The backend returned an empty schedule.")
        return schedule, alerts, audit_logs, True, "Live FastAPI data"
    except ApiClientError as exc:
        demo = load_demo_payload(APP_DIR / "fakejason.json")
        return (
            demo["schedule"],
            demo.get("alerts", []),
            demo.get("audit_logs", []),
            False,
            str(exc),
        )


def format_time(value: pd.Timestamp) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def format_audit_timestamp(value: object) -> str:
    try:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("Asia/Singapore")
        else:
            timestamp = timestamp.tz_convert("Asia/Singapore")
        return timestamp.strftime("%d %b %Y, %I:%M %p SGT").replace(", 0", ", ")
    except (TypeError, ValueError):
        return str(value)


def line_meta(line: object) -> dict[str, str]:
    code = str(line)
    return LINE_META.get(code, {"name": code, "color": "#8FA8BF", "class": "other"})


def render_jobs_table(schedule: pd.DataFrame) -> None:
    rows: list[str] = []
    status_classes = {
        "Done": "done",
        "Error": "error",
        "Delay": "delay",
        "In progress": "in-progress",
        "Not started": "not-started",
    }
    priority_classes = {"Urgent": "urgent", "High": "high", "Medium": "medium", "Low": "low"}

    ordered = schedule.assign(
        _line_order=schedule["line"].map({code: index for index, code in enumerate(LINE_META)}).fillna(len(LINE_META))
    ).sort_values(["_line_order", "track", "scheduled_start"], kind="stable")

    for row in ordered.to_dict("records"):
        meta = line_meta(row["line"])
        status = str(row["status"])
        priority = str(row["priority"])
        rows.append(
            f'<tr><td class="time-cell">{escape(format_time(row["scheduled_start"]))}</td>'
            f'<td class="time-cell">{escape(format_time(row["scheduled_end"]))}</td>'
            f'<td><span class="line-badge line-{meta["class"]}">{escape(str(row["line"]))}</span></td>'
            f'<td><span class="track-badge">{escape(str(row["track"]))}</span></td>'
            f'<td class="job-cell">{escape(str(row["name"]))}</td>'
            f'<td class="engineer-cell">{escape(str(row["engineer_text"]))}</td>'
            f'<td><span class="priority-pill priority-{priority_classes.get(priority, "medium")}">{escape(priority)}</span></td>'
            f'<td><span class="status-pill status-{status_classes.get(status, "not-started")}">'
            f'<i></i>{escape(status)}</span></td></tr>'
        )

    st.markdown(
        '<div class="jobs-table-wrap"><table class="jobs-table">'
        '<thead><tr><th>Start (SGT)</th><th>End (SGT)</th><th>Line</th><th>Track</th>'
        '<th>Job</th><th>Engineers</th><th>Priority</th><th>Status</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def connection_markup(is_live: bool) -> str:
    label = "Connected" if is_live else "Demo data"
    detail = "Live FastAPI data" if is_live else "Backend unavailable"
    css_class = "live" if is_live else "demo"
    return f"""
    <div class="connection-pill {css_class}">
      <span class="connection-dot"></span>
      <div><strong>{label}</strong><small>{detail}</small></div>
    </div>
    """


def render_header(is_live: bool) -> None:
    title_col, action_col = st.columns([6.4, 1.2], vertical_alignment="center")
    with title_col:
        st.markdown(
            """
            <div class="page-heading">
              <div>
                <h1>Tonight's maintenance plan</h1>
                <p>Engineering window: 12:30 AM - 5:00 AM (4h 30m)</p>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with action_col:
        st.markdown(connection_markup(is_live), unsafe_allow_html=True)


def build_timeline(schedule: pd.DataFrame) -> object:
    chart_rows: list[dict] = []
    for row in schedule.to_dict("records"):
        chart_rows.append(
            {
                **row,
                "display_type": row["status"],
                "bar_label": row["name"],
            }
        )
        chart_rows.append(
            {
                **row,
                "scheduled_start": row["scheduled_end"],
                "scheduled_end": row["scheduled_end"] + timedelta(minutes=30),
                "display_type": "Buffer",
                "bar_label": "30m buffer",
            }
        )

    chart_df = pd.DataFrame(chart_rows)
    category_order: list[str] = []
    # Plotly draws categorical rows from the bottom upward, so line groups are
    # supplied in reverse display order to keep NS, EW, then CCL from top to bottom.
    unknown_lines = [line for line in schedule["line"].unique() if line not in LINE_META]
    ordered_lines = unknown_lines + [line for line in reversed(LINE_META) if line in schedule["line"].values]
    for line in ordered_lines:
        line_rows = schedule[schedule["line"] == line]
        line_tracks = list(dict.fromkeys(line_rows["track_label"].tolist()))
        category_order.extend(reversed(line_tracks))
    category_labels: list[str] = []
    for label in category_order:
        line, track = label.split(" · ", maxsplit=1)
        meta = line_meta(line)
        category_labels.append(
            f"<span style='color:{meta['color']}'><b>■ {escape(line)}</b></span>  <b>{escape(track)}</b>"
        )
    fig = px.timeline(
        chart_df,
        x_start="scheduled_start",
        x_end="scheduled_end",
        y="track_label",
        color="display_type",
        text="bar_label",
        color_discrete_map={**STATUS_COLORS, "Buffer": "#52677D"},
        category_orders={
            "track_label": category_order,
            "display_type": ["Done", "In progress", "Delay", "Error", "Not started", "Buffer"],
        },
        custom_data=["name", "line", "track", "priority", "engineer_text"],
    )
    fig.update_traces(
        textposition="inside",
        insidetextanchor="start",
        textfont={"color": "#F4F7FB", "size": 12},
        marker_line_width=0,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Line: %{customdata[1]}<br>"
            "Track: %{customdata[2]}<br>"
            "Priority: %{customdata[3]}<br>"
            "Engineers: %{customdata[4]}<extra></extra>"
        ),
    )
    for trace in fig.data:
        if trace.name == "Buffer":
            trace.opacity = 0.58
            trace.hovertemplate = "<b>Safety buffer</b><br>30 minutes reserved<extra></extra>"

    for index, label in enumerate(category_order):
        line = label.split(" · ", maxsplit=1)[0]
        fig.add_hrect(
            y0=index - 0.48,
            y1=index + 0.48,
            fillcolor=line_meta(line)["color"],
            opacity=0.045,
            line_width=0,
            layer="below",
        )

    earliest_day = schedule["scheduled_start"].min().normalize()
    latest_day = schedule["scheduled_end"].max().normalize()
    chart_start = earliest_day.to_pydatetime() + timedelta(minutes=26)
    chart_end = latest_day.to_pydatetime() + timedelta(hours=5, minutes=8)
    if chart_end <= chart_start:
        chart_end += pd.Timedelta(days=1)

    fig.update_layout(
        height=500,
        margin={"l": 12, "r": 26, "t": 76, "b": 12},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0B1C2D",
        font={"family": "Inter, Segoe UI, sans-serif", "color": "#C5D4E6", "size": 12},
        hoverlabel={"bgcolor": "#12283D", "font_color": "#F4F7FB", "bordercolor": "#36516C"},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.13,
            "xanchor": "right",
            "x": 1,
            "title": None,
            "font": {"size": 11, "color": "#E6EEF7"},
            "bgcolor": "rgba(15,37,57,.95)",
            "bordercolor": "rgba(82,103,125,.55)",
            "borderwidth": 1,
        },
        xaxis={
            "range": [chart_start, chart_end],
            "dtick": 30 * 60 * 1000,
            "tickformat": "%I:%M\n%p",
            "showgrid": True,
            "gridcolor": "rgba(109,139,168,.22)",
            "zeroline": False,
            "title": None,
            "side": "top",
            "automargin": True,
            "tickfont": {"color": "#D7E4F0", "size": 11},
        },
        yaxis={
            "title": {"text": "LINE / TRACK", "font": {"size": 10, "color": "#7891AA"}},
            "autorange": "reversed",
            "showgrid": True,
            "gridcolor": "rgba(109,139,168,.18)",
            "tickmode": "array",
            "tickvals": category_order,
            "ticktext": category_labels,
            "tickfont": {"color": "#EAF1F8", "size": 12},
            "automargin": True,
        },
        bargap=0.36,
    )
    return fig


def render_recommendation(schedule: pd.DataFrame, conflicts: list[dict]) -> None:
    recommendation = build_recommendation(schedule, conflicts)
    affected_html = "".join(f"<li>{escape(item)}</li>" for item in recommendation["affected"])
    impact_html = "".join(
        f'<li><span class="impact-check">✓</span>{escape(item)}</li>'
        for item in recommendation["impact"]
    )
    st.markdown(
        f"""
        <section class="recommendation-panel">
          <div class="panel-kicker">AI recommendation <span>BETA</span></div>
          <h2>{escape(recommendation['title'])}</h2>
          <p>{escape(recommendation['summary'])}</p>
          <ul class="affected-list">{affected_html}</ul>
          <div class="suggested-action">
            <strong>Suggested action</strong>
            <p>{escape(recommendation['action'])}</p>
          </div>
          <div class="impact-title">Impact summary</div>
          <ul class="impact-list">{impact_html}</ul>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_operations(schedule: pd.DataFrame, is_live: bool, api_url: str) -> None:
    render_header(is_live)

    line_options = ["All lines", *sorted(schedule["line"].dropna().unique().tolist())]
    status_options = ["All statuses", *sorted(schedule["status"].dropna().unique().tolist())]
    priority_order = [p for p in ["Urgent", "High", "Medium", "Low"] if p in schedule["priority"].values]
    filter_cols = st.columns([1.25, 1.25, 1.25, 3.7, 0.95], vertical_alignment="bottom")
    with filter_cols[0]:
        selected_line = st.selectbox("MRT line", line_options)
    with filter_cols[1]:
        selected_status = st.selectbox("Status", status_options)
    with filter_cols[2]:
        selected_priority = st.selectbox("Priority", ["All priorities", *priority_order])
    with filter_cols[4]:
        if st.button("Refresh", width="stretch", type="secondary"):
            st.rerun()

    filtered = schedule.copy()
    if selected_line != "All lines":
        filtered = filtered[filtered["line"] == selected_line]
    if selected_status != "All statuses":
        filtered = filtered[filtered["status"] == selected_status]
    if selected_priority != "All priorities":
        filtered = filtered[filtered["priority"] == selected_priority]

    if filtered.empty:
        st.info("No maintenance jobs match these filters. Try clearing one of them.")
        return

    conflicts = detect_conflicts(filtered)
    chart_col, recommendation_col = st.columns([4.7, 1.45], gap="medium")
    with chart_col:
        st.markdown('<div class="section-title">Overnight schedule</div>', unsafe_allow_html=True)
        st.plotly_chart(build_timeline(filtered), width="stretch", config={"displayModeBar": False})
    with recommendation_col:
        render_recommendation(filtered, conflicts)
        if st.button("Review proposal", width="stretch", type="primary"):
            if is_live:
                try:
                    ApiClient(api_url).propose_schedule()
                    st.success("The backend generated a fresh schedule proposal.")
                except ApiClientError as exc:
                    st.error(f"Proposal request failed: {exc}")
            else:
                st.success("Demo proposal reviewed. Connect FastAPI to generate a live proposal.")

    st.markdown(
        f'<div class="section-title table-title">Scheduled jobs <span>{len(filtered)}</span></div>',
        unsafe_allow_html=True,
    )
    render_jobs_table(filtered)


def render_alerts(alerts: list[dict], is_live: bool) -> None:
    render_header(is_live)
    st.markdown('<div class="section-title">Active alerts</div>', unsafe_allow_html=True)
    if not alerts:
        st.success("No active maintenance alerts.")
        return
    st.dataframe(pd.DataFrame(alerts), width="stretch", hide_index=True)


def render_audit_log(audit_logs: list[dict], is_live: bool) -> None:
    render_header(is_live)
    st.markdown('<div class="section-title">Audit and approval history</div>', unsafe_allow_html=True)
    if not audit_logs:
        st.info("No audit records are available yet.")
        return
    audit_df = pd.DataFrame(audit_logs)
    if "timestamp" in audit_df:
        audit_df["timestamp"] = audit_df["timestamp"].map(format_audit_timestamp)
    audit_df = audit_df.rename(
        columns={
            "id": "ID",
            "timestamp": "Date and time",
            "action": "Action",
            "details": "Details",
            "approved_by": "Approved by",
        }
    )
    st.dataframe(audit_df, width="stretch", hide_index=True)


load_styles()

with st.sidebar:
    st.markdown(
        """
        <div class="brand-block">
          <strong>Ngeebula</strong>
          <span>Rail Maintenance</span>
          <small>Plan tonight. A safer tomorrow.</small>
        </div>
        """,
        unsafe_allow_html=True,
    )
    page = st.radio("Workspace", ["Operations", "Alerts", "Audit log"], label_visibility="collapsed")
    st.markdown('<div class="sidebar-spacer"></div>', unsafe_allow_html=True)
    api_url = st.text_input(
        "FastAPI URL",
        value=DEFAULT_API_URL,
        help="The frontend falls back to demo data if this API cannot be reached.",
    )
    st.caption("Frontend draft · Streamlit + Plotly")

raw_schedule, alerts, audit_logs, is_live, _connection_detail = get_dashboard_data(api_url)
schedule = normalise_schedule(raw_schedule)

if not is_live:
    st.markdown(
        '<div class="demo-banner"><strong>Demo mode:</strong> showing realistic sample data while FastAPI is unavailable.</div>',
        unsafe_allow_html=True,
    )

if page == "Operations":
    render_operations(schedule, is_live, api_url)
elif page == "Alerts":
    render_alerts(alerts, is_live)
else:
    render_audit_log(audit_logs, is_live)
