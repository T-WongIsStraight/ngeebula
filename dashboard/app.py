import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import io

API_URL = "http://localhost:8000/api"

st.set_page_config(page_title="LTA Track Possession Control Center", layout="wide")
st.title("🚊 LTA Railway Track Access Optimiser & Control Center")

# Navigation Tabs
tab_upload, tab_gantt, tab_checklist, tab_audit = st.tabs([
    "📁 Upload Input CSVs (Files 1–8)", 
    "📅 Interactive Gantt Chart", 
    "📋 Task Management Checklist", 
    "📜 Audit Log & History"
])

# -----------------------------------------------------------------------------
# TAB 0: CSV FILE UPLOADER
# -----------------------------------------------------------------------------
with tab_upload:
    st.subheader(" Upload Input Datasets (01 to 08)")
    st.markdown("Upload your custom CSV datasets below. Once uploaded, the solver will process them dynamically.")
    
    col1, col2 = st.columns(2)
    
    required_files = {
        "01_LINES.csv": "Lines Master Data",
        "02_STATIONS.csv": "Stations Master Data",
        "03_SECTORS.csv": "Track Sectors & Mappings",
        "04_LOCATION_SUPPLY.csv": "Nightly Location Supply",
        "05_BUFFER_LOCATION.csv": "Exclusion Buffer Rules",
        "06_PARAMETERS.csv": "System Parameters & ECLO Multipliers",
        "07_PROJECT_DETAILS.csv": "Contract Details & Deadlines",
        "08_ACTIVITY_DETAILS.csv": "Activity Demand Book"
    }
    
    uploaded_files = {}
    
    for idx, (filename, label) in enumerate(required_files.items()):
        target_col = col1 if idx % 2 == 0 else col2
        uploaded_files[filename] = target_col.file_uploader(f"Upload `{filename}` ({label})", type=["csv"], key=filename)

    st.markdown("---")
    if st.button("🚀 Process & Upload Files to Backend", type="primary"):
        files_to_send = []
        for filename, file_obj in uploaded_files.items():
            if file_obj is not None:
                files_to_send.append(("files", (filename, file_obj.getvalue(), "text/csv")))
        
        if files_to_send:
            try:
                res = requests.post(f"{API_URL}/upload-datasets", files=files_to_send, timeout=15)
                if res.status_code == 200:
                    st.success(f" Successfully processed and loaded {len(files_to_send)} input dataset files into the solver backend!")
                else:
                    st.error(f"Failed to upload files: {res.text}")
            except Exception as e:
                st.error(f"Error connecting to backend API: {e}")
        else:
            st.warning("Please upload at least one CSV file before submitting.")

# -----------------------------------------------------------------------------
# TAB 1: GANTT CHART & SOLVER EXECUTION
# -----------------------------------------------------------------------------
with tab_gantt:
    st.subheader("Nightly Track Possessions Schedule & Solver Engine")
    
    col_a, col_b = st.columns([2, 1])
    with col_a:
        scenario = st.selectbox("Select Optimization Scenario", ["A (Strict Supply)", "B (Strict Schedule)", "C (Elastic Trade-Off)"])
        scenario_code = scenario[0]
    
    with col_b:
        st.markdown("<br>", unsafe_allow_html=True)
        run_solver = st.button("⚡ Run Solver & Generate Schedule Outputs", type="primary")

    if run_solver:
        with st.spinner("Running CP-SAT Constraint Optimization Solver..."):
            try:
                res = requests.get(f"{API_URL}/solve/{scenario_code}", timeout=30).json()
                if res:
                    st.session_state["schedule_data"] = res
                    st.success(" Solver execution complete! Generated SCHEDULE_ACCESS.csv, SCHEDULE_OCCUPANCY.csv, and RESULTS.csv.")
                else:
                    st.warning("No valid schedule returned by solver.")
            except Exception as e:
                st.error(f"Failed to run optimization solver: {e}")

    # Render Gantt Chart
    if "schedule_data" in st.session_state and st.session_state["schedule_data"]:
        df_gantt = pd.DataFrame(st.session_state["schedule_data"])
        fig = px.timeline(
            df_gantt,
            x_start="week",
            x_end="week",
            y="activity_id",
            color="contract_number",
            title=f"Generated Track Possession Timeline - Scenario {scenario_code}"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Download Output Files Buttons
        st.markdown("### 📥 Download Submission CSV Outputs")
        d_col1, d_col2, d_col3 = st.columns(3)
        
        csv_access = requests.get(f"{API_URL}/download/SCHEDULE_ACCESS.csv").text
        csv_occupancy = requests.get(f"{API_URL}/download/SCHEDULE_OCCUPANCY.csv").text
        csv_results = requests.get(f"{API_URL}/download/RESULTS.csv").text
        
        d_col1.download_button("💾 Download SCHEDULE_ACCESS.csv", csv_access, "SCHEDULE_ACCESS.csv", "text/csv")
        d_col2.download_button("💾 Download SCHEDULE_OCCUPANCY.csv", csv_occupancy, "SCHEDULE_OCCUPANCY.csv", "text/csv")
        d_col3.download_button("💾 Download RESULTS.csv", csv_results, "RESULTS.csv", "text/csv")

# -----------------------------------------------------------------------------
# TAB 2: TASK CHECKLIST & CRUD
# -----------------------------------------------------------------------------
with tab_checklist:
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
            st.warning("No tasks loaded. Please upload 08_ACTIVITY_DETAILS.csv in Tab 1.")
    except Exception as e:
        st.error(f"Error connecting to backend API: {e}")

# -----------------------------------------------------------------------------
# TAB 3: AUDIT LOG & HISTORY
# -----------------------------------------------------------------------------
with tab_audit:
    st.subheader("System Change Audit Trail & Log History")
    try:
        logs = requests.get(f"{API_URL}/audit-log", timeout=3).json()
        if logs:
            df_logs = pd.DataFrame(logs)
            st.dataframe(df_logs[['timestamp', 'log_id', 'action_type', 'activity_id', 'author', 'changes', 'replan_triggered']], use_container_width=True)
        else:
            st.info("No audit logs recorded yet.")
    except Exception:
        st.warning("Audit log system offline or initializing...")
