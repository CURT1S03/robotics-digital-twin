"""Experiments page — list all experiments and create new ones."""

from __future__ import annotations

import streamlit as st

from components import api_client as api


def render():
    st.header("Experiments")

    # ── Create new experiment ─────────────────────────────────────────── #
    with st.expander("➕  New Experiment", expanded=False):
        with st.form("new_experiment"):
            col1, col2 = st.columns(2)

            name = col1.text_input("Name", placeholder="my-waypoint-run-01")

            try:
                planners = api.list_planners()
                planner_options = {p["name"]: p["id"] for p in planners}
            except Exception:
                planner_options = {"Waypoint Follower": "waypoint", "RRT Planner": "rrt"}

            planner_label = col1.selectbox("Planner", list(planner_options.keys()))
            planner_type = planner_options[planner_label]

            try:
                scenarios = api.list_scenarios()
                scenario_options = [s["name"] for s in scenarios]
            except Exception:
                scenario_options = ["straight_line", "obstacle_course"]

            scenario_name = col2.selectbox("Scenario", scenario_options)
            num_trials = col2.number_input("Trials", min_value=1, max_value=20, value=3)
            max_steps = col1.number_input("Max Steps", min_value=100, max_value=20000, value=2000, step=100)
            headless = col2.checkbox("Headless", value=True)

            submitted = st.form_submit_button("Create Experiment")
            if submitted:
                if not name.strip():
                    st.error("Name is required.")
                else:
                    try:
                        exp = api.create_experiment(
                            name=name.strip(),
                            planner_type=planner_type,
                            scenario_name=scenario_name,
                            num_trials=int(num_trials),
                            max_steps=int(max_steps),
                            headless=headless,
                        )
                        st.success(f"Created experiment #{exp['experiment_id']}: {exp['experiment_name']}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to create experiment: {e}")

    st.divider()

    # ── Experiment list ───────────────────────────────────────────────── #
    try:
        experiments = api.list_experiments(limit=50)
    except Exception as e:
        st.error(f"Cannot reach API: {e}")
        return

    if not experiments:
        st.info("No experiments yet. Create one above.")
        return

    _status_colors = {
        "queued": "⬜",
        "running": "🔵",
        "completed": "🟢",
        "failed": "🔴",
        "stopped": "🟡",
    }

    for exp in experiments:
        icon = _status_colors.get(exp["status"], "⬜")
        label = f"{icon} **#{exp['experiment_id']}** — {exp['experiment_name']} `{exp['planner_type']}` / `{exp['scenario_name']}`"

        with st.expander(label, expanded=False):
            col1, col2, col3 = st.columns([2, 2, 1])
            col1.metric("Status", exp["status"].capitalize())
            col1.caption(f"Created: {exp['created_at'][:19]}")
            if exp.get("finished_at"):
                col2.caption(f"Finished: {exp['finished_at'][:19]}")

            # Controls
            if exp["status"] in ("queued", "completed", "failed", "stopped"):
                if col3.button("▶ Run next trial", key=f"run_{exp['experiment_id']}"):
                    try:
                        result = api.run_experiment(exp["experiment_id"])
                        st.success(f"Trial {result['trial_number']} started (run_id={result['run_id']})")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            elif exp["status"] == "running":
                if col3.button("⏹ Stop", key=f"stop_{exp['experiment_id']}"):
                    try:
                        api.stop_experiment(exp["experiment_id"])
                        st.warning("Stop signal sent.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            # Runs table
            try:
                detail = api.get_experiment(exp["experiment_id"])
                runs = detail.get("plan_runs", [])
                if runs:
                    import pandas as pd
                    df = pd.DataFrame(runs)[
                        ["run_id", "trial_number", "status", "goal_reached"]
                    ].rename(columns={
                        "run_id": "Run ID",
                        "trial_number": "Trial",
                        "status": "Status",
                        "goal_reached": "Goal Reached",
                    })
                    st.dataframe(df, use_container_width=True, hide_index=True)
            except Exception:
                pass
