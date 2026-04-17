"""ROS bridge service — connects the mock ROS 2 pub/sub layer to the database
and to WebSocket clients in the Streamlit dashboard.

Architecture:
    SimManager subprocess  ──stdout──▶  SimManager._read_output()
                                              │
                                              ▼ on_output callback
                                        ROSBridgeService.handle_event()
                                         ├─ persist robot state to DB
                                         ├─ persist metrics to DB
                                         └─ broadcast to WebSocket queues
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from ros_mock import registry
from ros_mock.messages import OdometryMsg, PerformanceMetricsMsg, PlanStatusMsg

logger = logging.getLogger(__name__)


class ROSBridgeService:
    """Receives structured events from the sim subprocess and fans them out.

    Call ``initialize(session_factory)`` once during app lifespan, then pass
    ``handle_event`` as the *on_output* callback to ``SimManager.start_experiment``.
    """

    def __init__(self) -> None:
        self._session_factory = None
        # WebSocket client queues — one per connected dashboard tab
        self._ws_queues: list[asyncio.Queue] = []

    # ── Lifecycle ──────────────────────────────────────────────────────── #

    def initialize(self, session_factory) -> None:  # noqa: ANN001
        self._session_factory = session_factory
        logger.info("ROSBridgeService initialised.")

    def shutdown(self) -> None:
        # Drain and close all WebSocket queues
        for q in self._ws_queues:
            try:
                q.put_nowait(None)   # sentinel — tells consumers to close
            except asyncio.QueueFull:
                pass
        self._ws_queues.clear()

    # ── WebSocket fan-out ──────────────────────────────────────────────── #

    def add_ws_client(self) -> asyncio.Queue:
        """Register a new WebSocket consumer; returns its dedicated queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        self._ws_queues.append(q)
        logger.debug("WS client added (total=%d)", len(self._ws_queues))
        return q

    def remove_ws_client(self, queue: asyncio.Queue) -> None:
        try:
            self._ws_queues.remove(queue)
            logger.debug("WS client removed (total=%d)", len(self._ws_queues))
        except ValueError:
            pass

    def _broadcast(self, event: dict) -> None:
        """Non-blocking fan-out to all registered WebSocket queues."""
        dead: list[asyncio.Queue] = []
        for q in self._ws_queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._ws_queues.remove(q)

    # ── Event handler (called from SimManager stdout reader) ───────────── #

    def handle_event(self, event: dict) -> None:
        """Dispatch a structured JSON event emitted by run_experiment.py."""
        event_type = event.get("type")
        self._broadcast(event)   # always forward to WebSocket clients

        if event_type == "odometry":
            asyncio.ensure_future(self._persist_odometry(event))
        elif event_type == "metrics":
            asyncio.ensure_future(self._persist_metrics(event))
        elif event_type in ("plan_status", "done"):
            pass   # broadcast-only for now; metrics cover final state

    # ── DB persistence helpers ─────────────────────────────────────────── #

    async def _persist_odometry(self, event: dict) -> None:
        if self._session_factory is None:
            return
        from backend.db import crud

        run_id: int = event.get("run_id", 0)
        if not run_id:
            return
        try:
            async with self._session_factory() as db:
                await crud.add_robot_state(
                    db,
                    run_id=run_id,
                    sim_step=event.get("step", 0),
                    x=event.get("x", 0.0),
                    y=event.get("y", 0.0),
                    orientation=event.get("yaw", 0.0),
                    linear_vel=event.get("linear_x", 0.0),
                    angular_vel=event.get("angular_z", 0.0),
                )
        except Exception:
            logger.exception("Failed to persist odometry for run_id=%d", run_id)

    async def _persist_metrics(self, event: dict) -> None:
        if self._session_factory is None:
            return
        from backend.db import crud

        run_id: int = event.get("run_id", 0)
        goal_reached: bool = event.get("goal_reached", False)
        if not run_id:
            return

        metrics = {
            k: float(event[k])
            for k in (
                "path_length",
                "energy_consumed",
                "collision_count",
                "completion_time",
                "mean_tracking_error",
            )
            if k in event
        }

        try:
            async with self._session_factory() as db:
                if metrics:
                    await crud.add_metrics_bulk(db, run_id=run_id, metrics=metrics)
                await crud.update_plan_run(
                    db,
                    run_id=run_id,
                    status="completed",
                    goal_reached=goal_reached,
                    end_time=datetime.utcnow(),
                )
        except Exception:
            logger.exception("Failed to persist metrics for run_id=%d", run_id)
