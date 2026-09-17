import streamlit as st
import pandas as pd
import plotly.express as px
import requests

API_URL = "http://localhost:8000/api"

st.set_page_config(page_title="LTA Track Possession Control Center", layout="wide")
st.title("🚊 LTA Railway Track Access Optimiser & Control Center")

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
    st.subheader("Upload Input Datasets (01 to 08)")
    col1, col2 = st.columns(2)
    
    required_files = {
        "01_LINES.csv": "Lines Master Data",
        "02_STATIONS.csv": "Stations Master Data",
        "03_SECTORS.csv": "Track Sectors & Mappings",
        "04_LOCATION_SUPPLY.csv": "Nightly Location Supply",
        "05_BUFFER_LOCATION.csv": "Exclusion Buffer Rules",
        "06_PARAMETERS.csv": "System Parameters & Horizon",
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
                    st.success(f"Successfully loaded {len(files_to_send)} input dataset files into the backend!")
                else:
                    st.error(f"Failed to upload files: {res.text}")
            except Exception as e:
                st.error(f"Error connecting to backend API: {e}")
        else:
            st.warning("Please upload at least one CSV file.")

# -----------------------------------------------------------------------------
# TAB 1: GANTT CHART & SOLVER
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
                res = requests.get(f"{API_URL}/solve/{scenario_code}", timeout=30)
                if res.status_code == 200:
                    st.session_state["schedule_data"] = res.json()
                    st.success("Solver execution complete! Generated SCHEDULE_ACCESS.csv, SCHEDULE_OCCUPANCY.csv, and RESULTS.csv.")
                else:
                    st.error(f"Solver Error ({res.status_code}): {res.text}")
            except Exception as e:
                st.error(f"Failed to run optimization solver: {e}")

    if "schedule_data" in st.session_state and st.session_state["schedule_data"]:
        df_gantt = pd.DataFrame(st.session_state["schedule_data"])
        
        if not df_gantt.empty and "week" in df_gantt.columns:
            base_date_str = "2027-01-04"
            try:
                params_res = requests.get(f"{API_URL}/parameters", timeout=3).json()
                if params_res and "start_date" in params_res:
                    base_date_str = params_res["start_date"]
            except Exception:
                pass
                
            base_date = pd.to_datetime(base_date_str)

            df_gantt['start_date'] = df_gantt['week'].apply(lambda w: base_date + pd.Timedelta(weeks=int(float(w))-1))
            df_gantt['end_date'] = df_gantt['start_date'] + pd.Timedelta(days=6)

            fig = px.timeline(
                df_gantt,
                x_start="start_date",
                x_end="end_date",
                y="activity_id",
                color="contract_number" if "contract_number" in df_gantt.columns else None,
                title=f"Generated Track Possession Timeline - Scenario {scenario_code} (Horizon Start: {base_date_str})"
            )
            
            fig.update_yaxes(autorange="reversed")
            fig.update_layout(xaxis_title="Calendar Timeline")
            
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("### 📥 Download Submission CSV Outputs")
            d_col1, d_col2, d_col3 = st.columns(3)
            
            csv_access = requests.get(f"{API_URL}/download/SCHEDULE_ACCESS.csv").text
            csv_occupancy = requests.get(f"{API_URL}/download/SCHEDULE_OCCUPANCY.csv").text
            csv_results = requests.get(f"{API_URL}/download/RESULTS.csv").text
            
            d_col1.download_button("💾 Download SCHEDULE_ACCESS.csv", csv_access, "SCHEDULE_ACCESS.csv", "text/csv")
            d_col2.download_button("💾 Download SCHEDULE_OCCUPANCY.csv", csv_occupancy, "SCHEDULE_OCCUPANCY.csv", "text/csv")
            d_col3.download_button("💾 Download RESULTS.csv", csv_results, "RESULTS.csv", "text/csv")

# -----------------------------------------------------------------------------
# TAB 2: TASK CHECKLIST & EDITING
# -----------------------------------------------------------------------------
with tab_checklist:
    st.subheader("Activity Workload Checklist")
    try:
        response = requests.get(f"{API_URL}/tasks", timeout=5)
        if response.status_code == 200:
            tasks = response.json()
            if tasks:
                df_tasks = pd.DataFrame(tasks)
                
                avail_cols = df_tasks.columns.tolist()
                display_cols = [c for c in ['activity_id', 'contract_number', 'nature_of_works', 'total_accesses_required', 'status'] if c in avail_cols]
                
                if not display_cols:
                    display_cols = avail_cols[:5]
                
                edited_df = st.data_editor(
                    df_tasks[display_cols],
                    column_config={
                        "status": st.column_config.SelectboxColumn("Status", options=["Not Started", "In Progress", "Done"])
                    },
                    disabled=[c for c in display_cols if c != "status"],
                    use_container_width=True
                )
                
                if st.button("💾 Save Status Changes"):
                    for _, row in edited_df.iterrows():
                        requests.post(f"{API_URL}/tasks/update", json={
                            "activity_id": str(row['activity_id']),
                            "status": str(row['status']),
                            "author": "Works_Controller_UI"
                        }, timeout=3)
                    st.success("Changes saved and audit log updated!")
                    st.rerun()
            else:
                st.info("No activity tasks loaded yet. Upload `08_ACTIVITY_DETAILS.csv` on the Upload tab.")
        else:
            st.error(f"Backend API Error ({response.status_code}): {response.text}")
    except Exception as e:
        st.error(f"Error connecting to backend API: {e}")

# -----------------------------------------------------------------------------
# TAB 3: AUDIT LOG & HISTORY
# -----------------------------------------------------------------------------
with tab_audit:
    st.subheader("System Change Audit Trail & Log History")
    try:
        response = requests.get(f"{API_URL}/audit-log", timeout=3)
        if response.status_code == 200:
            logs = response.json()
            if logs:
                df_logs = pd.DataFrame(logs)
                display_cols = [c for c in ['timestamp', 'log_id', 'action_type', 'activity_id', 'author', 'changes', 'replan_triggered'] if c in df_logs.columns]
                st.dataframe(df_logs[display_cols], use_container_width=True)
            else:
                st.info("No audit logs recorded yet.")
        else:
            st.warning("Audit log endpoint returned non-200 status.")
    except Exception:
        st.warning("Audit log system offline or initializing...")
