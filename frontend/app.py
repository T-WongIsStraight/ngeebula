import streamlit as st
import json
import pandas as pd
import plotly.express as px

# Page setup
st.set_page_config(page_title="Rail Maintenance Scheduler", layout="wide")
st.title("🚆 Rail Maintenance Scheduler")

# Load fake JSON (later this becomes an API call to Jeremiah's backend)
# Real version: data = requests.post("http://localhost:8000/schedule/run").json()
with open("fakejason.json", "r") as f:
    data = json.load(f)

schedule = data["schedule"]
ai_explanation = data["ai_explanation"]

# --- AI Explanation ---
st.subheader("AI Explanation")
st.info(ai_explanation)

# --- Gantt Chart ---
st.subheader("Schedule Timeline")
df = pd.DataFrame(schedule)
fig = px.timeline(
    df,
    x_start="scheduled_start",
    x_end="scheduled_end",
    y="track",
    color="priority",
    hover_data=["name", "job_id", "line"],
)
fig.update_yaxes(autorange="reversed")
st.plotly_chart(fig, use_container_width=True)

# --- Raw job list ---
st.subheader("All Jobs")
st.dataframe(df, use_container_width=True)