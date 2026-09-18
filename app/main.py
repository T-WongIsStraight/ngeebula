import os
import io
import pandas as pd
from typing import List
from fastapi import FastAPI, UploadFile, File, Response
from app.solver import run_track_optimization

app = FastAPI(title="LTA Track Access Optimiser API")

DATA_DIR = "data"
OUTPUT_DIR = "output"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

activities_df = pd.DataFrame()
projects_df = pd.DataFrame()


@app.get("/api/health")
def health_check():
    return {"status": "ok", "loaded_activities": len(activities_df)}


@app.get("/api/parameters")
def get_parameters():
    param_path = os.path.join(DATA_DIR, "06_PARAMETERS.csv")
    if os.path.exists(param_path):
        try:
            df_params = pd.read_csv(param_path)
            if "key" in df_params.columns and "value" in df_params.columns:
                param_dict = dict(zip(df_params['key'], df_params['value']))
                return {
                    "start_date": str(param_dict.get("horizon_start", "2027-01-04")),
                    "horizon_weeks": int(param_dict.get("horizon_weeks", 30))
                }
        except Exception as e:
            print(f"Error reading 06_PARAMETERS.csv: {e}")
    return {"start_date": "2027-01-04", "horizon_weeks": 30}


@app.post("/api/upload-datasets")
async def upload_datasets(files: List[UploadFile] = File(...)):
    global activities_df, projects_df
    saved_files = []

    for file in files:
        file_path = os.path.join(DATA_DIR, file.filename)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        saved_files.append(file.filename)

        if file.filename == "08_ACTIVITY_DETAILS.csv":
            activities_df = pd.read_csv(io.BytesIO(content))
        elif file.filename == "07_PROJECT_DETAILS.csv":
            projects_df = pd.read_csv(io.BytesIO(content))

    return {"status": "success", "uploaded_files": saved_files}


@app.get("/api/solve/{scenario}")
def solve_schedule(scenario: str):
    global activities_df, projects_df

    if activities_df.empty and os.path.exists(os.path.join(DATA_DIR, "08_ACTIVITY_DETAILS.csv")):
        activities_df = pd.read_csv(os.path.join(DATA_DIR, "08_ACTIVITY_DETAILS.csv"))
    if projects_df.empty and os.path.exists(os.path.join(DATA_DIR, "07_PROJECT_DETAILS.csv")):
        projects_df = pd.read_csv(os.path.join(DATA_DIR, "07_PROJECT_DETAILS.csv"))

    access_df = run_track_optimization(
        activities_df=activities_df,
        projects_df=projects_df,
        scenario=scenario,
        output_dir=OUTPUT_DIR
    )

    if access_df.empty:
        return []

    return access_df.to_dict(orient="records")


@app.get("/api/download/{filename}")
def download_file(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            content = f.read()
        return Response(content=content, media_type="text/csv")
    else:
        return Response(content="activity_id,access_seq,week,eclo,access_night\n", media_type="text/csv")
