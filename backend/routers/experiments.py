"""Experiment CRUD endpoints."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db import crud
from backend.schemas import (
    ExperimentCreate,
    ExperimentDetail,
    ExperimentSummary,
    ExperimentAggregates,
    PlanRunSummary,
    MetricResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentSummary, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    payload: ExperimentCreate, db: AsyncSession = Depends(get_db)
):
    """Create a new experiment definition."""
    config = {
        "num_trials": payload.num_trials,
        "max_steps": payload.max_steps,
        "headless": payload.headless,
        "planner_params": payload.planner_params,
    }
    exp = await crud.create_experiment(
        db,
        name=payload.name,
        planner_type=payload.planner_type,
        scenario_name=payload.scenario_name,
        config_json=json.dumps(config),
    )
    return exp


@router.get("", response_model=list[ExperimentSummary])
async def list_experiments(
    limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)
):
    return await crud.list_experiments(db, limit=limit, offset=offset)


@router.get("/{experiment_id}", response_model=ExperimentDetail)
async def get_experiment(experiment_id: int, db: AsyncSession = Depends(get_db)):
    exp = await crud.get_experiment(db, experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp


@router.get("/{experiment_id}/aggregates", response_model=ExperimentAggregates)
async def get_experiment_aggregates(
    experiment_id: int, db: AsyncSession = Depends(get_db)
):
    """Return cross-trial aggregate statistics for an experiment."""
    exp = await crud.get_experiment(db, experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    runs = await crud.list_plan_runs(db, experiment_id)
    completed = [r for r in runs if r.status == "completed"]

    def _avg(metric_name: str) -> float | None:
        vals = []
        for run in completed:
            for m in run.metrics:
                if m.metric_name == metric_name:
                    vals.append(m.metric_value)
        return round(sum(vals) / len(vals), 4) if vals else None

    return ExperimentAggregates(
        experiment_id=experiment_id,
        planner_type=exp.planner_type,
        scenario_name=exp.scenario_name,
        num_completed_trials=len(completed),
        goal_reached_count=sum(1 for r in completed if r.goal_reached),
        avg_path_length=_avg("path_length"),
        avg_completion_time=_avg("completion_time"),
        avg_energy=_avg("energy_consumed"),
        avg_tracking_error=_avg("mean_tracking_error"),
        avg_collisions=_avg("collision_count"),
    )
