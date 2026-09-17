import os
import pandas as pd
from typing import Dict, Tuple

DATA_DIR = os.getenv("DATA_DIR", "data")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

def load_all_input_data(data_dir: str = DATA_DIR) -> Dict[str, pd.DataFrame]:
    """Loads all 8 input datasets for Problem Statement 1 into a dictionary of DataFrames."""
    files = {
        "lines": "01_LINES.csv",
        "stations": "02_STATIONS.csv",
        "sectors": "03_SECTORS.csv",
        "supply": "04_LOCATION_SUPPLY.csv",
        "buffers": "05_BUFFER_LOCATION.csv",
        "params": "06_PARAMETERS.csv",
        "projects": "07_PROJECT_DETAILS.csv",
        "activities": "08_ACTIVITY_DETAILS.csv"
    }
    
    data = {}
    for key, filename in files.items():
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            data[key] = pd.read_csv(filepath)
        else:
            # Fallback to current working directory if data folder isn't populated
            if os.path.exists(filename):
                data[key] = pd.read_csv(filename)
            else:
                raise FileNotFoundError(f"Required dataset {filename} not found in {data_dir} or root directory.")
    return data

def export_submission_files(
    access_df: pd.DataFrame, 
    occupancy_df: pd.DataFrame, 
    results_df: pd.DataFrame, 
    output_dir: str = OUTPUT_DIR
) -> Tuple[str, str, str]:
    """Exports generated schedule DataFrames to the required 3 CSV submission files."""
    os.makedirs(output_dir, exist_ok=True)
    
    access_path = os.path.join(output_dir, "SCHEDULE_ACCESS.csv")
    occupancy_path = os.path.join(output_dir, "SCHEDULE_OCCUPANCY.csv")
    results_path = os.path.join(output_dir, "RESULTS.csv")
    
    access_df.to_csv(access_path, index=False)
    occupancy_df.to_csv(occupancy_path, index=False)
    results_df.to_csv(results_path, index=False)
    
    return access_path, occupancy_path, results_path
