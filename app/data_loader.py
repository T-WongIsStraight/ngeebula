import os
import pandas as pd
from typing import Dict, Any, Tuple
from app.solver import load_instance, write_submission

DATA_DIR = os.getenv("DATA_DIR", "data")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

def load_all_input_data(data_dir: str = DATA_DIR) -> Dict[str, Any]:
    """Loads input CSVs using solver's canonical parser."""
    return load_instance(data_dir)

def export_submission_files(
    access_df: pd.DataFrame, 
    occupancy_df: pd.DataFrame, 
    results_df: pd.DataFrame, 
    output_dir: str = OUTPUT_DIR
) -> Tuple[str, str, str]:
    """Helper to export generated dataframes matching official submission files."""
    os.makedirs(output_dir, exist_ok=True)
    
    access_path = os.path.join(output_dir, "SCHEDULE_ACCESS.csv")
    occupancy_path = os.path.join(output_dir, "SCHEDULE_OCCUPANCY.csv")
    results_path = os.path.join(output_dir, "RESULTS.csv")
    
    access_df.to_csv(access_path, index=False)
    occupancy_df.to_csv(occupancy_path, index=False)
    results_df.to_csv(results_path, index=False)
    
    return access_path, occupancy_path, results_path
