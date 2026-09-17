import streamlit as st
import pandas as pd
import requests

def render_audit_log_view(api_url: str):
    """Displays system change audit logs and history."""
    st.markdown("### 📜 System Change Audit Trail & Log History")
    
    try:
        res = requests.get(f"{api_url}/audit-log")
        if res.status_code != 200:
            st.error("Could not retrieve audit history.")
            return
        logs = res.json()
    except Exception as e:
        st.error(f"Backend connection error: {e}")
        return

    if not logs:
        st.info("No audit logs recorded yet.")
        return

    df_logs = pd.DataFrame(logs)
    
    # Render Log Table
    st.dataframe(
        df_logs[["timestamp", "log_id", "action_type", "activity_id", "author", "replan_triggered", "changes"]],
        column_config={
            "timestamp": "Timestamp",
            "log_id": "Log ID",
            "action_type": "Action",
            "activity_id": "Activity",
            "author": "Author",
            "replan_triggered": "Re-planned?",
            "changes": "Modified Fields (Diff)"
        },
        use_container_width=True
    )
