import streamlit as st
import pandas as pd
import requests

def render_task_checklist(api_url: str):
    """Renders the editable task checklist table and controls."""
    st.markdown("### 📋 Activity Workload & Status Checklist")
    
    try:
        response = requests.get(f"{api_url}/tasks")
        if response.status_code != 200:
            st.error("Failed to fetch tasks from backend server.")
            return
        tasks_data = response.json()
    except Exception as e:
        st.error(f"Backend connection error: {e}")
        return

    df = pd.DataFrame(tasks_data)
    
    # Checklist Table Editor
    edited_df = st.data_editor(
        df[["activity_id", "contract_number", "nature_of_works", "total_accesses", "status"]],
        column_config={
            "status": st.column_config.SelectboxColumn(
                "Current Status",
                options=["Not Started", "In Progress", "Done"],
                help="Update task completion status"
            ),
            "total_accesses": st.column_config.NumberColumn("Required Accesses", min_value=1)
        },
        disabled=["activity_id", "contract_number", "nature_of_works"],
        use_container_width=True,
        key="checklist_editor"
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("💾 Save Changes"):
            for _, row in edited_df.iterrows():
                payload = {
                    "activity_id": row["activity_id"],
                    "status": row["status"],
                    "total_accesses": float(row["total_accesses"]),
                    "author": "Works_Controller_UI"
                }
                requests.post(f"{api_url}/tasks/update", json=payload)
            st.success("Task updates saved & audit log created!")
            st.rerun()
