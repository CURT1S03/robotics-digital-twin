"""Algorithm comparison page — overlay metrics across experiments."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from dashboard.components import api_client as api
from dashboard.components.charts import (
    metrics_bar_chart,
    multi_trajectory_chart,
)

_METRIC_LABELS = {
    "path_length": "Path Length (m)",
    "energy_consumed": "Energy Consumed",
    "collision_count": "Collisions",
    "completion_time": "Completion Time (s)",
    "mean_tracking_error": "Mean Tracking Error (m)",
}


def render():
    st.header("Algorithm Comparison")
    st.caption("Select two or more completed experiments to compare side-by-side.")

    # ── Load experiment list ──────────────────────────────────────────── #
    try:
        all_experiments = api.list_experiments(limit=100)
    except Exception as e:
        st.error(f"Cannot reach API: {e}")
        return

    completed = [e for e in all_experiments if e["status"] == "completed"]
    if len(completed) < 2:
        st.info("You need at least **2 completed experiments** to compare. Run some experiments first.")
        return

    options = {f"#{e['experiment_id']} {e['experiment_name']} [{e['planner_type']}]": e["experiment_id"] for e in completed}
    selected_labels = st.multiselect(
        "Select experiments",
        list(options.keys()),
        default=list(options.keys())[:2],
    )

    if len(selected_labels) < 2:
        st.warning("Select at least 2 experiments.")
        return

    selected_ids = [options[lbl] for lbl in selected_labels]

    # ── Fetch aggregates ──────────────────────────────────────────────── #
    agg_data = []
    for exp_id in selected_ids:
        try:
            agg = api.get_aggregates(exp_id)
            label = next(lbl for lbl, eid in options.items() if eid == exp_id)
            agg_data.append({"label": label, "metrics": agg, "experiment_id": exp_id})
        except Exception:
            pass

    if not agg_data:
        st.error("Failed to load aggregates.")
        return

    # ── Summary table ─────────────────────────────────────────────────── #
    st.subheader("Summary")
    summary_rows = []
    for d in agg_data:
        a = d["metrics"]
        summary_rows.append({
            "Experiment": d["label"],
            "Planner": a.get("planner_type", ""),
            "Scenario": a.get("scenario_name", ""),
            "Trials": a.get("num_completed_trials", 0),
            "Goal Reached": a.get("goal_reached_count", 0),
            "Avg Path (m)": a.get("avg_path_length"),
            "Avg Time (s)": a.get("avg_completion_time"),
            "Avg Error (m)": a.get("avg_tracking_error"),
            "Avg Collisions": a.get("avg_collisions"),
        })
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── Metric bar charts ─────────────────────────────────────────────── #
    st.subheader("Metric Comparison")
    col1, col2 = st.columns(2)

    chart_data = [
        {
            "label": d["label"],
            "metrics": {
                "path_length": d["metrics"].get("avg_path_length") or 0,
                "energy_consumed": d["metrics"].get("avg_energy") or 0,
                "collision_count": d["metrics"].get("avg_collisions") or 0,
                "completion_time": d["metrics"].get("avg_completion_time") or 0,
                "mean_tracking_error": d["metrics"].get("avg_tracking_error") or 0,
            },
        }
        for d in agg_data
    ]

    with col1:
        st.plotly_chart(
            metrics_bar_chart(chart_data, "path_length", "Average Path Length (m)"),
            use_container_width=True,
        )
        st.plotly_chart(
            metrics_bar_chart(chart_data, "collision_count", "Average Collisions"),
            use_container_width=True,
        )

    with col2:
        st.plotly_chart(
            metrics_bar_chart(chart_data, "completion_time", "Average Completion Time (s)"),
            use_container_width=True,
        )
        st.plotly_chart(
            metrics_bar_chart(chart_data, "mean_tracking_error", "Average Tracking Error (m)"),
            use_container_width=True,
        )

    # ── Trajectory comparison ─────────────────────────────────────────── #
    st.divider()
    st.subheader("Trajectory Overlay (latest trial per experiment)")

    traj_runs = []
    for d in agg_data:
        try:
            detail = api.get_experiment(d["experiment_id"])
            runs = detail.get("plan_runs", [])
            completed_runs = [r for r in runs if r["status"] == "completed"]
            if not completed_runs:
                continue
            latest_run = completed_runs[-1]
            traj = api.get_trajectory(latest_run["run_id"])
            if traj:
                traj_runs.append({"label": d["label"], "trajectory": traj})
        except Exception:
            pass

    if traj_runs:
        st.plotly_chart(multi_trajectory_chart(traj_runs), use_container_width=True)
    else:
        st.info("No trajectory data available for the selected experiments.")
