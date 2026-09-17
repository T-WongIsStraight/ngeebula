import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

def render_gantt_chart(schedule_df: pd.DataFrame, activities_df: pd.DataFrame):
    """Generates an interactive Plotly timeline for track possessions."""
    if schedule_df.empty:
        st.warning("No schedule data available to display Gantt chart.")
        return

    # Merge schedule with activity metadata
    df = schedule_df.merge(activities_df, on="activity_id", how="left")
    
    # Calculate dummy start/end date visualization from week numbers
    df["start_week"] = df["week"]
    df["end_week"] = df["week"] + 1

    fig = px.timeline(
        df,
        x_start="start_week",
        x_end="end_week",
        y="activity_id",
        color="contract_number",
        hover_data=["nature_of_works", "start_location_id", "end_location_id", "eclo"],
        title="Nightly Track Possession Timeline by Activity & Contract",
        labels={"activity_id": "Activity ID", "start_week": "Week"}
    )

    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        height=500,
        margin=dict(l=20, r=20, t=40, b=20),
        xaxis_title="Timeline (Weeks)",
        legend_title="Contract Number"
    )
    
    st.plotly_chart(fig, use_container_width=True)
