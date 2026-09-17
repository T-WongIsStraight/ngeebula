import streamlit as st
import pandas as pd
import plotly.express as px
import requests

API_URL = "http://localhost:8000/api"

st.set_page_config(page_title="LTA Track Possession Control Center", layout="wide")
st.title("🚊 LTA Railway Track Access Optimiser & Control Center")

tab1, tab2, tab3 = st.tabs(["📅 Interactive Gantt Chart", "📋 Task Management Checklist", "📜 Audit Log & History"])

# TAB 1: GANTT CHART
with tab1:
    st.subheader("Nightly Track Possessions Schedule")
    scenario = st.selectbox("Select Scenario Strategy", ["A (Strict Supply)", "B (Strict Schedule)", "C (Elastic Trade-Off)"])
    scenario_code = scenario[0]
    
    if st.button("🔄 Run / Refresh Schedule Optimization"):
        try:
            res = requests.get(f"{API_URL}/solve/{scenario_code}", timeout=10).json()
            if res:
                df_gantt = pd.DataFrame(res)
                fig = px.timeline(
                    df_gantt,
                    x_start="week",
                    x_end="week",
                    y="activity_id",
                    color="contract_number",
                    title=f"Possession Timeline - Scenario {scenario_code}"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No schedule generated.")
        except Exception as e:
            st.error(f"Failed to communicate with optimization solver API: {e}")

# TAB 2: TASK CHECKLIST & CRUD
with tab2:
    st.subheader("Activity Workload Checklist")
    try:
        tasks = requests.get(f"{API_URL}/tasks", timeout=3).json()
        if tasks:
            df_tasks = pd.DataFrame(tasks)
            edited_df = st.data_editor(
                df_tasks[['activity_id', 'contract_number', 'nature_of_works', 'total_accesses', 'status']],
                column_config={
                    "status": st.column_config.SelectboxColumn("Status", options=["Not Started", "In Progress", "Done"])
                },
                disabled=["activity_id", "contract_number"],
                use_container_width=True
            )
            
            if st.button("💾 Save Status Changes"):
                for _, row in edited_df.iterrows():
                    requests.post(f"{API_URL}/tasks/update", json={
                        "activity_id": row['activity_id'],
                        "status": row['status'],
                        "author": "Works_Controller_UI"
                    }, timeout=3)
                st.success("Changes saved and audit log updated!")
                st.rerun()
        else:
            st.warning("No tasks found in backend.")
    except requests.exceptions.ConnectionError:
        st.warning("⚠️ Connecting to Backend API (http://localhost:8000)... Please wait a moment and click refresh.")
    except Exception as e:
        st.error(f"Error loading task checklist: {e}")

# TAB 3: AUDIT LOG & HISTORY
with tab3:
    st.subheader("System Change Audit Trail & Log History")
    try:
        logs = requests.get(f"{API_URL}/audit-log", timeout=3).json()
        if logs:
            df_logs = pd.DataFrame(logs)
            st.dataframe(df_logs[['timestamp', 'log_id', 'action_type', 'activity_id', 'author', 'changes', 'replan_triggered']], use_container_width=True)
        else:
            st.info("No audit logs recorded yet.")
    except Exception:
        st.warning("⚠️ Audit log system offline or initializing...")
