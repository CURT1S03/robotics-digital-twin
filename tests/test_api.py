"""API endpoint smoke tests (no Isaac Sim required)."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ── Configure pytest-asyncio ────────────────────────────────────────────────── #
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="module")
async def client():
    """Spin up the FastAPI app with an in-memory SQLite database."""
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    from backend.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ─── Health ──────────────────────────────────────────────────────────────────── #

async def test_health(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["sim_state"] == "idle"


# ─── Experiments CRUD ────────────────────────────────────────────────────────── #

async def test_create_experiment(client: AsyncClient):
    resp = await client.post(
        "/api/experiments",
        json={
            "name": "test-waypoint",
            "planner_type": "waypoint",
            "scenario_name": "straight_line",
            "num_trials": 2,
            "max_steps": 500,
            "headless": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["experiment_name"] == "test-waypoint"
    assert data["planner_type"] == "waypoint"
    assert data["status"] == "queued"
    return data["experiment_id"]


async def test_list_experiments(client: AsyncClient):
    # Ensure at least one experiment exists
    await client.post(
        "/api/experiments",
        json={"name": "list-test", "planner_type": "rrt", "scenario_name": "obstacle_course"},
    )
    resp = await client.get("/api/experiments")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


async def test_get_experiment_not_found(client: AsyncClient):
    resp = await client.get("/api/experiments/99999")
    assert resp.status_code == 404


async def test_get_experiment_detail(client: AsyncClient):
    create_resp = await client.post(
        "/api/experiments",
        json={"name": "detail-test", "planner_type": "waypoint", "scenario_name": "straight_line"},
    )
    exp_id = create_resp.json()["experiment_id"]
    resp = await client.get(f"/api/experiments/{exp_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["experiment_id"] == exp_id
    assert "plan_runs" in data


# ─── Sim status ────────────────────────────────────────────────────────────── #

async def test_experiment_status_when_idle(client: AsyncClient):
    create_resp = await client.post(
        "/api/experiments",
        json={"name": "status-test", "planner_type": "waypoint", "scenario_name": "straight_line"},
    )
    exp_id = create_resp.json()["experiment_id"]
    resp = await client.get(f"/api/experiments/{exp_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "idle"


# ─── Config endpoints ────────────────────────────────────────────────────────── #

async def test_list_planners(client: AsyncClient):
    resp = await client.get("/api/config/planners")
    assert resp.status_code == 200
    planners = resp.json()
    ids = [p["id"] for p in planners]
    assert "waypoint" in ids
    assert "rrt" in ids
