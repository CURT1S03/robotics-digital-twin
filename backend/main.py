"""FastAPI application entry point.

Run with:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.db.database import async_session, init_db
from backend.db import crud
from backend.routers import experiments, planning, metrics
from backend.services.sim_manager import SimManager
from backend.services.ros_bridge import ROSBridgeService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Shared service instances ──────────────────────────────────────────────── #
sim_manager = SimManager()
ros_bridge = ROSBridgeService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("Initialising database…")
    await init_db()
    logger.info("Database ready.")

    # Mark any experiments that were 'running' at crash/restart as failed
    async with async_session() as db:
        stale = await crud.mark_stale_experiments(db)
        if stale:
            logger.info("Marked %d stale experiment(s) as failed.", stale)

    # Wire services into routers
    ros_bridge.initialize(async_session)
    planning.set_services(sim_manager, ros_bridge)
    metrics.set_services(ros_bridge)

    yield

    # Cleanup
    logger.info("Shutting down…")
    ros_bridge.shutdown()
    await sim_manager.stop(timeout=10.0)


# ── App ──────────────────────────────────────────────────────────────────── #
app = FastAPI(
    title="Robotics Digital Twin API",
    description=(
        "Orchestrate Go2 navigation planning validation experiments in "
        "NVIDIA Omniverse Isaac Lab."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",   # Streamlit default port
        "http://127.0.0.1:8501",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(experiments.router)
app.include_router(planning.router)
app.include_router(metrics.router)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "sim_state": sim_manager.state.value,
        "current_experiment_id": sim_manager.current_experiment_id,
        "current_run_id": sim_manager.current_run_id,
    }


@app.get("/api/config/scenarios")
async def list_scenarios():
    """Return available scenario names (YAML files in sim/assets/scenarios/)."""
    import yaml
    from pathlib import Path

    scenario_dir = settings.project_root / "sim" / "assets" / "scenarios"
    scenarios = []
    for f in sorted(scenario_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text())
            scenarios.append({
                "name": f.stem,
                "description": data.get("description", ""),
                "difficulty": data.get("difficulty", "medium"),
            })
        except Exception:
            scenarios.append({"name": f.stem, "description": "", "difficulty": "unknown"})
    return scenarios


@app.get("/api/config/planners")
async def list_planners():
    """Return available planner types."""
    return [
        {"id": "waypoint", "name": "Waypoint Follower", "description": "Proportional velocity controller following pre-defined waypoints."},
        {"id": "rrt", "name": "RRT Planner", "description": "Rapidly-exploring Random Tree path planner with waypoint following."},
    ]
