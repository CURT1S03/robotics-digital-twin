"""Metrics and telemetry endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db import crud
from backend.schemas import MetricResponse, TrajectoryPoint
from backend.services.ros_bridge import ROSBridgeService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["metrics"])

_ros_bridge: ROSBridgeService | None = None


def set_services(ros_bridge: ROSBridgeService) -> None:
    global _ros_bridge
    _ros_bridge = ros_bridge


# ── REST endpoints ──────────────────────────────────────────────────────────── #

@router.get("/api/metrics/{run_id}", response_model=list[MetricResponse])
async def get_metrics(run_id: int, db: AsyncSession = Depends(get_db)):
    """All performance metrics for a single trial run."""
    return await crud.get_metrics_for_run(db, run_id)


@router.get("/api/metrics/{run_id}/trajectory", response_model=list[TrajectoryPoint])
async def get_trajectory(run_id: int, db: AsyncSession = Depends(get_db)):
    """Robot state history (trajectory) for a single trial run."""
    states = await crud.get_trajectory(db, run_id)
    return states


@router.get("/api/runs/{run_id}", response_model=dict)
async def get_run_detail(run_id: int, db: AsyncSession = Depends(get_db)):
    """Detailed info about a specific plan run including metrics."""
    run = await crud.get_plan_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": run.run_id,
        "experiment_id": run.experiment_id,
        "trial_number": run.trial_number,
        "status": run.status,
        "goal_reached": run.goal_reached,
        "start_time": run.start_time,
        "end_time": run.end_time,
        "metrics": [
            {"name": m.metric_name, "value": m.metric_value} for m in run.metrics
        ],
    }


# ── WebSocket endpoint ──────────────────────────────────────────────────────── #

@router.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    """Stream live experiment events to connected clients (e.g. Streamlit dashboard)."""
    if _ros_bridge is None:
        await websocket.close(code=1011, reason="ROSBridgeService not initialised")
        return

    await websocket.accept()
    queue = _ros_bridge.add_ws_client()
    logger.info("WebSocket telemetry client connected")

    try:
        import json as _json

        while True:
            event = await queue.get()
            if event is None:
                break  # sentinel from shutdown
            await websocket.send_text(_json.dumps(event))
    except WebSocketDisconnect:
        logger.info("WebSocket telemetry client disconnected")
    except Exception:
        logger.exception("WebSocket error")
    finally:
        _ros_bridge.remove_ws_client(queue)
