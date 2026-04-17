"""Reusable Plotly chart helpers for the Streamlit dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# ─── Trajectory ───────────────────────────────────────────────────────────── #

def trajectory_chart(
    trajectory_points: list[dict],
    scenario_obstacles: list[dict] | None = None,
    goal: dict | None = None,
    title: str = "Robot Trajectory",
) -> go.Figure:
    """2-D top-down trajectory plot with optional obstacles and goal."""
    fig = go.Figure()

    if trajectory_points:
        df = pd.DataFrame(trajectory_points)
        fig.add_trace(
            go.Scatter(
                x=df["position_x"],
                y=df["position_y"],
                mode="lines+markers",
                name="Trajectory",
                line=dict(color="royalblue", width=2),
                marker=dict(size=4),
            )
        )
        # Start and end markers
        fig.add_trace(
            go.Scatter(
                x=[df["position_x"].iloc[0]],
                y=[df["position_y"].iloc[0]],
                mode="markers",
                name="Start",
                marker=dict(size=12, color="green", symbol="star"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[df["position_x"].iloc[-1]],
                y=[df["position_y"].iloc[-1]],
                mode="markers",
                name="End",
                marker=dict(size=12, color="red", symbol="x"),
            )
        )

    # Goal marker
    if goal:
        fig.add_trace(
            go.Scatter(
                x=[goal["x"]],
                y=[goal["y"]],
                mode="markers",
                name="Goal",
                marker=dict(size=14, color="orange", symbol="diamond"),
            )
        )

    # Obstacles as circles (approximated with scatter)
    if scenario_obstacles:
        for obs in scenario_obstacles:
            r = obs.get("radius", 0.5)
            theta_range = [i * 6.28 / 36 for i in range(37)]
            fig.add_trace(
                go.Scatter(
                    x=[obs["x"] + r * __import__("math").cos(t) for t in theta_range],
                    y=[obs["y"] + r * __import__("math").sin(t) for t in theta_range],
                    mode="lines",
                    fill="toself",
                    fillcolor="rgba(220,50,50,0.3)",
                    line=dict(color="red", width=1),
                    name=f"Obstacle @({obs['x']},{obs['y']})",
                    showlegend=False,
                )
            )

    fig.update_layout(
        title=title,
        xaxis_title="X (m)",
        yaxis_title="Y (m)",
        yaxis_scaleanchor="x",
        height=400,
        margin=dict(l=40, r=20, t=40, b=40),
    )
    return fig


def multi_trajectory_chart(
    runs: list[dict],  # [{"label": str, "trajectory": list[dict]}]
    title: str = "Trajectory Comparison",
) -> go.Figure:
    """Overlay multiple trajectories on one chart."""
    fig = go.Figure()
    colors = px.colors.qualitative.Plotly

    for i, run in enumerate(runs):
        pts = run.get("trajectory", [])
        if not pts:
            continue
        df = pd.DataFrame(pts)
        fig.add_trace(
            go.Scatter(
                x=df["position_x"],
                y=df["position_y"],
                mode="lines",
                name=run.get("label", f"Run {i+1}"),
                line=dict(color=colors[i % len(colors)], width=2),
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="X (m)",
        yaxis_title="Y (m)",
        yaxis_scaleanchor="x",
        height=420,
        margin=dict(l=40, r=20, t=40, b=40),
    )
    return fig


# ─── Metrics bar chart ────────────────────────────────────────────────────── #

def metrics_bar_chart(
    experiments: list[dict],  # [{"label": str, "metrics": {name: value}}]
    metric_name: str,
    title: str | None = None,
) -> go.Figure:
    labels = [e["label"] for e in experiments]
    values = [e["metrics"].get(metric_name, 0.0) for e in experiments]
    fig = px.bar(
        x=labels,
        y=values,
        labels={"x": "Experiment", "y": metric_name.replace("_", " ").title()},
        title=title or metric_name.replace("_", " ").title(),
        color=labels,
        color_discrete_sequence=px.colors.qualitative.Plotly,
    )
    fig.update_layout(height=350, margin=dict(l=40, r=20, t=40, b=40), showlegend=False)
    return fig


# ─── Metrics over trials ──────────────────────────────────────────────────── #

def metrics_line_chart(
    trials: list[dict],  # [{"trial": int, "value": float}]
    metric_name: str,
    title: str | None = None,
) -> go.Figure:
    if not trials:
        return go.Figure()
    df = pd.DataFrame(trials)
    fig = px.line(
        df,
        x="trial",
        y="value",
        markers=True,
        title=title or metric_name.replace("_", " ").title(),
        labels={"trial": "Trial #", "value": metric_name.replace("_", " ").title()},
    )
    fig.update_layout(height=300, margin=dict(l=40, r=20, t=40, b=40))
    return fig
