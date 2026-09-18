import os
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import dataclass
from ortools.sat.python import cp_model


# =============================================================================
# MODULE 5: MULTI-OBJECTIVE SCENARIO CONFIGURATION
# =============================================================================
@dataclass
class ScenarioConfig:
    name: str
    late_weight: dict
    allow_eclo: bool = True
    excess_cap: int | None = 0     # 0 = strictly forbidden, 1 = max 1 over, None = elastic
    hard_deadlines: bool = False   # True = late_days must be 0
    eclo_cost: int = 5             # 5 penalty points per ECLO night
    excess_cost: int = 7           # 7 penalty points per excess night over capacity


SCENARIOS = {
    "A": ScenarioConfig(
        name="Scenario A (Strict Supply)",
        late_weight={1: 100, 2: 10, 3: 1},
        allow_eclo=False,
        excess_cap=0,
        hard_deadlines=False,
    ),
    "B": ScenarioConfig(
        name="Scenario B (Strict Schedule)",
        late_weight={1: 100, 2: 10, 3: 1},
        allow_eclo=True,
        excess_cap=None,
        hard_deadlines=True,
    ),
    "C": ScenarioConfig(
        name="Scenario C (Elastic Trade-Off)",
        late_weight={1: 100, 2: 10, 3: 1},
        allow_eclo=True,
        excess_cap=1,
        hard_deadlines=False,
    ),
}


# =============================================================================
# MODULE 1: DATA INGESTION & SCHEMA ALIGNMENT
# =============================================================================
def ingest_and_align_datasets(activities_df: pd.DataFrame, projects_df: pd.DataFrame):
    """
    Cleans raw inputs, standardizes string keys, and parses baseline project dates.
    """
    activities_df = activities_df.copy()
    projects_df = projects_df.copy()

    for col in ['activity_id', 'contract_number']:
        if col in activities_df.columns:
            activities_df[col] = activities_df[col].astype(str).str.strip()
        if col in projects_df.columns:
            projects_df[col] = projects_df[col].astype(str).str.strip()

    return activities_df, projects_df


# =============================================================================
# MODULE 2: NETWORK GRAPH & SPATIAL PRECOMPUTATION ENGINE
# =============================================================================
def precompute_spatial_buffers(activities_df: pd.DataFrame):
    """
    Generates track sector spots and 2-sector spatial exclusion buffers,
    including Eastbound/Westbound (EB/WB) bound mirroring for Live Rail power cuts.
    """
    spots_lookup = {}
    buffer_lookup = {}

    for _, a in activities_df.iterrows():
        a_id = str(a['activity_id']).strip()
        start_loc = str(a.get('start_location_id', 'SEC:ALP:S15_S16:EB')).strip()
        end_loc = str(a.get('end_location_id', start_loc)).strip()
        
        spots = [start_loc] if start_loc == end_loc else [start_loc, end_loc]
        spots_lookup[a_id] = spots

        nature = str(a.get('nature_of_works', 'Non-live (Others)'))
        buffers = set(spots)

        # Live Rail 750V Power Cuts: Add bound mirroring (EB <-> WB)
        if "Live" in nature:
            for spot in spots:
                if ":EB" in spot:
                    buffers.add(spot.replace(":EB", ":WB"))
                elif ":WB" in spot:
                    buffers.add(spot.replace(":WB", ":EB"))
        
        buffer_lookup[a_id] = list(buffers)

    return spots_lookup, buffer_lookup


# =============================================================================
# UNIFIED SOLVER PIPELINE (MODULES 3 - 6)
# =============================================================================
def run_track_optimization(
    activities_df: pd.DataFrame,
    projects_df: pd.DataFrame,
    scenario: str = "A",
    output_dir: str = "output"
) -> pd.DataFrame:
    """
    Main Solver Pipeline executing Modules 1 through 6.
    """
    # --- MODULE 1 EXECUTION ---
    activities_df, projects_df = ingest_and_align_datasets(activities_df, projects_df)
    
    # --- MODULE 2 EXECUTION ---
    spots_lookup, buffer_lookup = precompute_spatial_buffers(activities_df)

    config = SCENARIOS.get(scenario.upper(), SCENARIOS["A"])
    model = cp_model.CpModel()

    # Horizon parameters
    horizon_weeks = 30
    W = list(range(1, horizon_weeks + 1))  # 30 Weeks
    N = list(range(1, 8))                  # 7 Nights (1=Mon ... 7=Sun)
    
    base_date = datetime(2027, 1, 4)

    activities = activities_df['activity_id'].tolist() if not activities_df.empty else []
    contracts = projects_df['contract_number'].unique().tolist() if not projects_df.empty else []

    # Parse metadata
    need = {}
    earliest = {}
    contract_of = {}
    nature_of = {}
    pred_of = {}

    acc_col = 'total_accesses_required' if 'total_accesses_required' in activities_df.columns else 'total_accesses'

    for _, a in activities_df.iterrows():
        a_id = a['activity_id']
        contract_of[a_id] = a.get('contract_number', 'C101')
        need[a_id] = int(a.get(acc_col, 1))
        
        p_start_str = str(a.get('planned_start_date', '2027-01-04'))
        try:
            p_start = pd.to_datetime(p_start_str)
            e_week = max(1, min(30, ((p_start - base_date).days // 7) + 1))
        except Exception:
            e_week = 1
        earliest[a_id] = e_week
        
        nature_of[a_id] = str(a.get('nature_of_works', 'Non-live (Others)'))
        pred_of[a_id] = str(a.get('predecessor_activity_id', '')).strip() if pd.notna(a.get('predecessor_activity_id')) else None

    priority = {}
    nights_per_week = {}
    workfronts = {}
    deadline_week = {}

    for _, p in projects_df.iterrows():
        c_num = p['contract_number']
        priority[c_num] = int(p.get('contract_priority', 3))
        nights_per_week[c_num] = int(p.get('number_of_maximum_access_per_week', 3))
        
        wf_col = 'number_of_workfronts' if 'number_of_workfronts' in p else 'workfronts'
        workfronts[c_num] = int(p.get(wf_col, 2))
        
        t_date_str = str(p.get('target_completion_date', '2027-08-01'))
        try:
            t_date = pd.to_datetime(t_date_str)
            d_week = max(1, min(30, ((t_date - base_date).days // 7) + 1))
        except Exception:
            d_week = 30
        deadline_week[c_num] = d_week

    # --- MODULE 3: DECISION VARIABLES & INTEGER ARITHMETIC ---
    # x[a, w, n] = 1 if activity 'a' runs in week 'w' on night 'n'
    x = {}
    # e[a, w, n] = 1 if Extended Closing (ECLO) is active (yields 3 progress units instead of 2)
    e = {}
    for a in activities:
        for w in W:
            for n in N:
                x[a, w, n] = model.NewBoolVar(f"x_{a}_w{w}_n{n}")
                e[a, w, n] = model.NewBoolVar(f"e_{a}_w{w}_n{n}")

    # Weekly active flag
    x_week = {}
    for a in activities:
        for w in W:
            x_week[a, w] = model.NewBoolVar(f"xweek_{a}_w{w}")
            model.AddMaxEquality(x_week[a, w], [x[a, w, n] for n in N])

    # Location overbooking slack variable
    all_spots = list(set(loc for spot_list in spots_lookup.values() for loc in spot_list)) if spots_lookup else ["LOC_DEFAULT"]
    over = {}
    for loc in all_spots:
        for w in W:
            max_over = 1 if config.excess_cap == 1 else (0 if config.excess_cap == 0 else 5)
            over[loc, w] = model.NewIntVar(0, max_over, f"over_{loc}_w{w}")

    # Contract completion tracking
    last_week = {}
    for a in activities:
        last_week[a] = model.NewIntVar(0, 30, f"last_week_{a}")
        for w in W:
            model.Add(last_week[a] >= w * x_week[a, w])

    finish_week = {}
    late_weeks = {}
    for c in contracts:
        c_acts = [a for a in activities if contract_of[a] == c]
        finish_week[c] = model.NewIntVar(0, 30, f"finish_{c}")
        if c_acts:
            model.AddMaxEquality(finish_week[c], [last_week[a] for a in c_acts])
        else:
            model.Add(finish_week[c] == 0)

        late_weeks[c] = model.NewIntVar(0, 30, f"late_{c}")
        model.Add(late_weeks[c] >= finish_week[c] - deadline_week.get(c, 30))

    # --- MODULE 4: HARD CONSTRAINT MATRIX ---

    # 1. Workload Fulfillment (Scaled Integer Progress: Standard = 2 units, ECLO = 3 units)
    for a in activities:
        total_progress = sum(2 * x[a, w, n] + e[a, w, n] for w in W for n in N)
        model.Add(total_progress >= 2 * need[a])

        for w in W:
            for n in N:
                if not config.allow_eclo:
                    model.Add(e[a, w, n] == 0)
                else:
                    model.Add(e[a, w, n] <= x[a, w, n])

    # 2. Planned Start Date Bounds & Predecessor Dependencies
    for a in activities:
        for w in range(1, earliest[a]):
            for n in N:
                model.Add(x[a, w, n] == 0)

        pred_id = pred_of[a]
        if pred_id and pred_id in activities:
            for w in W:
                model.Add(finish_week[contract_of[pred_id]] < w).OnlyEnforceIf(x_week[a, w])

    # 3. Weekly Access Caps & Concurrent Workfront Limits
    for c in contracts:
        c_acts = [a for a in activities if contract_of[a] == c]
        cap_nights = nights_per_week.get(c, 3)
        max_teams = workfronts.get(c, 2)

        for w in W:
            night_active = [model.NewBoolVar(f"nactive_{c}_w{w}_n{n}") for n in N]
            for n in N:
                model.AddMaxEquality(night_active[n - 1], [x[a, w, n] for a in c_acts])
            model.Add(sum(night_active) <= cap_nights)

            for n in N:
                model.Add(sum(x[a, w, n] for a in c_acts) <= max_teams)

    # 4. Spatial Safety Buffer Exclusions
    for i, a1 in enumerate(activities):
        for a2 in activities[i + 1:]:
            if set(buffer_lookup.get(a1, [])).intersection(set(spots_lookup.get(a2, []))):
                if "Live" in nature_of[a1] and "Live" in nature_of[a2]:
                    for w in W:
                        for n in N:
                            model.Add(x[a1, w, n] + x[a2, w, n] <= 1)

    # --- MODULE 5: MULTI-OBJECTIVE SCENARIO SELECTION ---
    objective_terms = []

    # Contract Overrun Costs
    for c in contracts:
        if config.hard_deadlines:
            model.Add(late_weeks[c] == 0)
        else:
            p_lvl = priority.get(c, 3)
            w_factor = config.late_weight.get(p_lvl, 1) * 7
            objective_terms.append(w_factor * late_weeks[c])

    # ECLO Usage Costs (5 pts per night)
    if config.allow_eclo:
        total_eclo = sum(e[a, w, n] for a in activities for w in W for n in N)
        objective_terms.append(config.eclo_cost * total_eclo)

    # Overbooking Costs (7 pts per excess night)
    total_excess = sum(over[loc, w] for loc in all_spots for w in W)
    objective_terms.append(config.excess_cost * total_excess)

    model.Minimize(sum(objective_terms))

    # --- MODULE 6: CP-SAT SOLVER EXECUTION & EXPORTERS ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15.0
    solver.parameters.num_workers = 4

    status = solver.Solve(model)

    access_records = []
    occupancy_records = []
    results_records = []

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for a in activities:
            seq = 0
            for w in W:
                for n in N:
                    if solver.Value(x[a, w, n]) == 1:
                        seq += 1
                        is_eclo = solver.Value(e[a, w, n])

                        access_records.append({
                            "activity_id": a,
                            "access_seq": seq,
                            "week": w,
                            "eclo": is_eclo,
                            "access_night": n
                        })

                        for loc in spots_lookup.get(a, ["SEC:ALP:S15_S16:EB"]):
                            occupancy_records.append({
                                "activity_id": a,
                                "week": w,
                                "location_id": loc,
                                "co_share_group": "GRP1"
                            })

        for c in contracts:
            f_w = solver.Value(finish_week[c])
            if f_w > 0:
                comp_date = base_date + timedelta(days=7 * f_w - 1)
                comp_date_str = comp_date.strftime("%Y-%m-%d")
            else:
                comp_date_str = "N/A"

            l_days = solver.Value(late_weeks[c]) * 7

            results_records.append({
                "scenario": scenario.upper(),
                "contract_number": c,
                "simulated_completion_date": comp_date_str,
                "overrun_days": l_days
            })

    # Save outputs to CSV files
    os.makedirs(output_dir, exist_ok=True)
    df_access = pd.DataFrame(access_records)
    df_occupancy = pd.DataFrame(occupancy_records)
    df_results = pd.DataFrame(results_records)

    df_access.to_csv(os.path.join(output_dir, "SCHEDULE_ACCESS.csv"), index=False)
    df_occupancy.to_csv(os.path.join(output_dir, "SCHEDULE_OCCUPANCY.csv"), index=False)
    df_results.to_csv(os.path.join(output_dir, "RESULTS.csv"), index=False)

    return df_access
