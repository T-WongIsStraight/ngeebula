from ortools.sat.python import cp_model
import pandas as pd

def run_track_optimization(activities_df, projects_df, scenario="A"):
    model = cp_model.CpModel()
    horizon_weeks = 12  # Standard 12-week schedule horizon
    
    # Decision Variables
    # x[a, w] = 1 if activity a is active in week w
    x = {}
    for _, act in activities_df.iterrows():
        a_id = act['activity_id']
        for w in range(1, horizon_weeks + 1):
            x[a_id, w] = model.NewBoolVar(f"x_{a_id}_w{w}")

    # Constraint 1: Workload Fulfillment (total_accesses must be completed)
    for _, act in activities_df.iterrows():
        a_id = act['activity_id']
        required_accesses = int(act['total_accesses'])
        model.Add(sum(x[a_id, w] for w in range(1, horizon_weeks + 1)) >= required_accesses)

    # Constraint 2: Contract Weekly Access Caps
    proj_caps = projects_df.set_index('contract_number')['number_of_maximum_access_per_week'].to_dict()
    for proj_id, cap in proj_caps.items():
        proj_acts = activities_df[activities_df['contract_number'] == proj_id]['activity_id'].tolist()
        for w in range(1, horizon_weeks + 1):
            model.Add(sum(x[a_id, w] for a_id in proj_acts) <= cap)

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)

    results = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for _, act in activities_df.iterrows():
            a_id = act['activity_id']
            for w in range(1, horizon_weeks + 1):
                if solver.Value(x[a_id, w]) == 1:
                    results.append({
                        "activity_id": a_id,
                        "contract_number": act['contract_number'],
                        "week": w,
                        "access_night": 1,
                        "eclo": 0,
                        "status": "In Progress"
                    })
    return pd.DataFrame(results)
