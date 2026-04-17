"""Live monitor page — auto-refreshing view of the active experiment."""

from __future__ import annotations

import time

import streamlit as st
import pandas as pd

from components import api_client as api
from components.charts import trajectory_chart, metrics_line_chart


def render():
    st.header("Live Monitor")

    # ── Sidebar controls ──────────────────────────────────────────────── #
    refresh = st.sidebar.toggle("Auto-refresh (2 s)", value=True)
    refresh_interval = 2.0

    # ── Backend health ────────────────────────────────────────────────── #
    try:
        health = api.health()
        state = health.get("sim_state", "unknown")
        exp_id = health.get("current_experiment_id")
        run_id = health.get("current_run_id")
    except Exception:
        st.error("⚠️  Cannot reach backend at http://localhost:8000. Is it running?")
        return

    status_icon = "🔵" if state == "running" else "⚫"
    st.metric("Simulator State", f"{status_icon} {state.capitalize()}")

    if state == "idle":
        st.info("No experiment is currently running. Start one from the **Experiments** page.")
        return

    st.caption(f"Experiment ID: `{exp_id}` | Run ID: `{run_id}`")

    # ── Live status ───────────────────────────────────────────────────── #
    try:
        status = api.get_sim_status(exp_id)
        if status.get("error_message"):
            st.error(f"Simulation error: {status['error_message']}")
    except Exception:
        pass

    col1, col2 = st.columns(2)
    col1.metric("Current Experiment", exp_id)
    col2.metric("Current Run ID", run_id)

    # ── Live trajectory ────────────────────────────────────────────────── #
    st.subheader("Live Trajectory")
    try:
        traj = api.get_trajectory(run_id)
        if traj:
            fig = trajectory_chart(traj, title=f"Run #{run_id} Trajectory")
            st.plotly_chart(fig, use_container_width=True)
            latest = traj[-1]
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("X (m)", f"{latest['position_x']:.3f}")
            mc2.metric("Y (m)", f"{latest['position_y']:.3f}")
            mc3.metric("Steps recorded", len(traj))
        else:
            st.info("Waiting for trajectory data…")
    except Exception as e:
        st.warning(f"Trajectory not yet available: {e}")

    # ── Live metrics ───────────────────────────────────────────────────── #
    st.subheader("Performance Metrics (last committed run)")
    try:
        metrics = api.get_metrics(run_id)
        if metrics:
            metric_by_name = {}
            for m in metrics:
                metric_by_name[m["metric_name"]] = m["metric_value"]
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Path Length (m)", f"{metric_by_name.get('path_length', 0):.3f}")
            mc2.metric("Completion Time (s)", f"{metric_by_name.get('completion_time', 0):.2f}")
            mc3.metric("Collisions", int(metric_by_name.get("collision_count", 0)))
            mc1.metric("Energy", f"{metric_by_name.get('energy_consumed', 0):.3f}")
            mc2.metric("Tracking Error (m)", f"{metric_by_name.get('mean_tracking_error', 0):.4f}")
        else:
            st.info("Metrics will appear when the run completes.")
    except Exception:
        pass

    # ── Auto-refresh ───────────────────────────────────────────────────── #
    if refresh:
        time.sleep(refresh_interval)
        st.rerun()
    else:
        if st.button("🔄  Refresh manually"):
            st.rerun()
