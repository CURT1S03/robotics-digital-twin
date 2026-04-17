"""Planning control endpoints — launch/stop experiments, query sim state."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db import crud
from backend.schemas import SimStatusResponse
from backend.services.sim_manager import SimManager, SimState
from backend.services.ros_bridge import ROSBridgeService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/experiments", tags=["planning"])

# ── Injected by main.py lifespan ─────────────────────────────────────────── #
_sim_manager: SimManager | None = None
_ros_bridge: ROSBridgeService | None = None


def set_services(sim_manager: SimManager, ros_bridge: ROSBridgeService) -> None:
    global _sim_manager, _ros_bridge
    _sim_manager = sim_manager
    _ros_bridge = ros_bridge


# ── Helpers ──────────────────────────────────────────────────────────────── #

def _require_sim() -> SimManager:
    if _sim_manager is None:
        raise HTTPException(status_code=503, detail="SimManager not initialised")
    return _sim_manager


# ── Endpoints ────────────────────────────────────────────────────────────── #

@router.post("/{experiment_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_experiment(
    experiment_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Launch the next trial for an experiment."""
    sim = _require_sim()

    if sim.state != SimState.IDLE:
        raise HTTPException(
            status_code=409,
            detail=f"Simulator is busy ({sim.state.value}). Stop the current run first.",
        )

    exp = await crud.get_experiment(db, experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    # Determine next trial number
    existing_runs = await crud.list_plan_runs(db, experiment_id)
    trial_number = len(existing_runs) + 1

    config = json.loads(exp.config_json or "{}")
    max_steps: int = config.get("max_steps", 2000)
    headless: bool = config.get("headless", True)
    planner_params: dict = config.get("planner_params", {})

    # Create DB record for this run
    plan_run = await crud.create_plan_run(db, experiment_id=experiment_id, trial_number=trial_number)
    await crud.update_plan_run(db, run_id=plan_run.run_id, status="running", start_time=datetime.utcnow())
    await crud.update_experiment_status(db, experiment_id=experiment_id, status="running")

    # Start subprocess
    log_dir = sim.start_experiment(
        experiment_id=experiment_id,
        run_id=plan_run.run_id,
        planner_type=exp.planner_type,
        scenario_name=exp.scenario_name,
        trial_number=trial_number,
        max_steps=max_steps,
        headless=headless,
        planner_params=planner_params,
        on_output=_ros_bridge.handle_event if _ros_bridge else None,
    )

    await crud.update_experiment_status(db, experiment_id=experiment_id, log_dir=log_dir, status="running")

    return {
        "message": "Experiment trial started",
        "experiment_id": experiment_id,
        "run_id": plan_run.run_id,
        "trial_number": trial_number,
        "log_dir": log_dir,
    }


@router.post("/{experiment_id}/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop_experiment(
    experiment_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Stop the currently running trial."""
    sim = _require_sim()

    if sim.state == SimState.IDLE:
        return {"message": "No experiment running"}

    if sim.current_experiment_id != experiment_id:
        raise HTTPException(
            status_code=409,
            detail=f"Running experiment is {sim.current_experiment_id}, not {experiment_id}",
        )

    run_id = sim.current_run_id
    await sim.stop(timeout=10.0)

    if run_id:
        await crud.update_plan_run(db, run_id=run_id, status="stopped", end_time=datetime.utcnow())
    await crud.update_experiment_status(
        db, experiment_id=experiment_id, status="stopped", finished_at=datetime.utcnow()
    )

    return {"message": "Stopped", "experiment_id": experiment_id, "run_id": run_id}


@router.get("/{experiment_id}/status", response_model=SimStatusResponse)
async def experiment_status(experiment_id: int):
    """Return the current simulator state."""
    sim = _require_sim()
    return SimStatusResponse(
        state=sim.state.value,
        experiment_id=sim.current_experiment_id,
        run_id=sim.current_run_id,
        log_dir=sim.log_dir,
        error_message=sim.last_error,
    )
