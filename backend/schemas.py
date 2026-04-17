"""Pydantic schemas for all API request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ─── Experiments ──────────────────────────────────────────────────────────── #

class ExperimentCreate(BaseModel):
    name: str = Field(description="Human-friendly experiment label.")
    planner_type: str = Field(
        default="waypoint",
        description="Planning algorithm: 'waypoint' or 'rrt'.",
    )
    scenario_name: str = Field(
        default="straight_line",
        description="Scenario file (without .yaml extension).",
    )
    num_trials: int = Field(default=3, ge=1, le=20)
    max_steps: int = Field(default=2000, ge=100, le=20000)
    headless: bool = Field(default=True)
    planner_params: dict = Field(default_factory=dict, description="Planner-specific hyperparameters.")


class ExperimentSummary(BaseModel):
    experiment_id: int
    experiment_name: str
    planner_type: str
    scenario_name: str
    status: str
    created_at: datetime
    finished_at: datetime | None = None

    class Config:
        from_attributes = True


class ExperimentDetail(ExperimentSummary):
    config_json: str
    log_dir: str | None = None
    plan_runs: list[PlanRunSummary] = []

    class Config:
        from_attributes = True


# ─── Plan Runs ──────────────────────────────────────────────────────────────── #

class PlanRunSummary(BaseModel):
    run_id: int
    experiment_id: int
    trial_number: int
    status: str
    goal_reached: bool
    start_time: datetime | None = None
    end_time: datetime | None = None

    class Config:
        from_attributes = True


class PlanRunDetail(PlanRunSummary):
    metrics: list[MetricResponse] = []

    class Config:
        from_attributes = True


# ─── Metrics ────────────────────────────────────────────────────────────────── #

class MetricResponse(BaseModel):
    metric_id: int
    run_id: int
    metric_name: str
    metric_value: float
    recorded_at: datetime

    class Config:
        from_attributes = True


class TrajectoryPoint(BaseModel):
    state_id: int
    run_id: int
    sim_step: int
    position_x: float
    position_y: float
    orientation: float
    linear_vel: float
    angular_vel: float
    recorded_at: datetime

    class Config:
        from_attributes = True


# ─── Simulation control ─────────────────────────────────────────────────────── #

class SimStatusResponse(BaseModel):
    state: str                          # idle | running | stopping
    experiment_id: int | None = None
    run_id: int | None = None
    trial_number: int | None = None
    log_dir: str | None = None
    error_message: str | None = None


# ─── Experiment summary (cross-run aggregates) ──────────────────────────────── #

class ExperimentAggregates(BaseModel):
    experiment_id: int
    planner_type: str
    scenario_name: str
    num_completed_trials: int
    goal_reached_count: int
    avg_path_length: float | None = None
    avg_completion_time: float | None = None
    avg_energy: float | None = None
    avg_tracking_error: float | None = None
    avg_collisions: float | None = None
