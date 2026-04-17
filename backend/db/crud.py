"""Async CRUD operations for all ORM models.

Keeps all DB logic out of routers and services — callers always receive
ORM objects or None/Sequence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import Experiment, PlanRun, PerformanceMetric, RobotState


# ─── Experiments ────────────────────────────────────────────────────────────── #

async def create_experiment(
    db: AsyncSession,
    name: str,
    planner_type: str,
    scenario_name: str,
    config_json: str = "{}",
) -> Experiment:
    exp = Experiment(
        experiment_name=name,
        planner_type=planner_type,
        scenario_name=scenario_name,
        config_json=config_json,
        status="queued",
    )
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    return exp


async def get_experiment(db: AsyncSession, experiment_id: int) -> Experiment | None:
    stmt = (
        select(Experiment)
        .where(Experiment.experiment_id == experiment_id)
        .options(selectinload(Experiment.plan_runs))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_experiments(
    db: AsyncSession, limit: int = 50, offset: int = 0
) -> Sequence[Experiment]:
    stmt = (
        select(Experiment)
        .order_by(Experiment.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def update_experiment_status(
    db: AsyncSession,
    experiment_id: int,
    status: str,
    finished_at: datetime | None = None,
    log_dir: str | None = None,
) -> Experiment | None:
    exp = await db.get(Experiment, experiment_id)
    if exp is None:
        return None
    exp.status = status
    if finished_at is not None:
        exp.finished_at = finished_at
    if log_dir is not None:
        exp.log_dir = log_dir
    await db.commit()
    await db.refresh(exp)
    return exp


async def mark_stale_experiments(db: AsyncSession) -> int:
    """Mark any running/queued experiments as failed (post-crash cleanup)."""
    stmt = (
        update(Experiment)
        .where(Experiment.status.in_(["running", "queued"]))
        .values(status="failed", finished_at=datetime.utcnow())
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount


# ─── Plan Runs ─────────────────────────────────────────────────────────────── #

async def create_plan_run(
    db: AsyncSession, experiment_id: int, trial_number: int
) -> PlanRun:
    run = PlanRun(
        experiment_id=experiment_id,
        trial_number=trial_number,
        status="queued",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def get_plan_run(db: AsyncSession, run_id: int) -> PlanRun | None:
    stmt = (
        select(PlanRun)
        .where(PlanRun.run_id == run_id)
        .options(
            selectinload(PlanRun.metrics),
            selectinload(PlanRun.robot_states),
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_plan_runs(
    db: AsyncSession, experiment_id: int
) -> Sequence[PlanRun]:
    stmt = (
        select(PlanRun)
        .where(PlanRun.experiment_id == experiment_id)
        .order_by(PlanRun.trial_number.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def update_plan_run(
    db: AsyncSession,
    run_id: int,
    status: str,
    goal_reached: bool = False,
    end_time: datetime | None = None,
    start_time: datetime | None = None,
) -> PlanRun | None:
    run = await db.get(PlanRun, run_id)
    if run is None:
        return None
    run.status = status
    run.goal_reached = goal_reached
    if end_time is not None:
        run.end_time = end_time
    if start_time is not None:
        run.start_time = start_time
    await db.commit()
    await db.refresh(run)
    return run


# ─── Performance Metrics ────────────────────────────────────────────────────── #

async def add_metric(
    db: AsyncSession, run_id: int, metric_name: str, metric_value: float
) -> PerformanceMetric:
    metric = PerformanceMetric(run_id=run_id, metric_name=metric_name, metric_value=metric_value)
    db.add(metric)
    await db.commit()
    await db.refresh(metric)
    return metric


async def add_metrics_bulk(
    db: AsyncSession, run_id: int, metrics: dict[str, float]
) -> list[PerformanceMetric]:
    """Insert multiple metrics in a single transaction."""
    records = [
        PerformanceMetric(run_id=run_id, metric_name=k, metric_value=v)
        for k, v in metrics.items()
    ]
    db.add_all(records)
    await db.commit()
    return records


async def get_metrics_for_run(
    db: AsyncSession, run_id: int
) -> Sequence[PerformanceMetric]:
    stmt = select(PerformanceMetric).where(PerformanceMetric.run_id == run_id)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_metrics_by_name_for_experiment(
    db: AsyncSession, experiment_id: int, metric_name: str
) -> Sequence[PerformanceMetric]:
    """Fetch all metrics with *metric_name* across all runs of an experiment."""
    stmt = (
        select(PerformanceMetric)
        .join(PlanRun, PlanRun.run_id == PerformanceMetric.run_id)
        .where(PlanRun.experiment_id == experiment_id)
        .where(PerformanceMetric.metric_name == metric_name)
        .order_by(PlanRun.trial_number.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ─── Robot States ───────────────────────────────────────────────────────────── #

async def add_robot_state(
    db: AsyncSession,
    run_id: int,
    sim_step: int,
    x: float,
    y: float,
    orientation: float,
    linear_vel: float,
    angular_vel: float,
) -> RobotState:
    state = RobotState(
        run_id=run_id,
        sim_step=sim_step,
        position_x=x,
        position_y=y,
        orientation=orientation,
        linear_vel=linear_vel,
        angular_vel=angular_vel,
    )
    db.add(state)
    await db.commit()
    await db.refresh(state)
    return state


async def get_trajectory(db: AsyncSession, run_id: int) -> Sequence[RobotState]:
    """Return all robot states for *run_id* ordered by sim_step."""
    stmt = (
        select(RobotState)
        .where(RobotState.run_id == run_id)
        .order_by(RobotState.sim_step.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()
