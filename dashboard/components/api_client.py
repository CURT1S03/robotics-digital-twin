"""Typed REST client for the Robotics Digital Twin FastAPI backend."""

from __future__ import annotations

import os
from typing import Any

import requests

_BASE_URL = os.getenv("DT_API_URL", "http://localhost:8000")
_TIMEOUT = 10.0


def _url(path: str) -> str:
    return f"{_BASE_URL}{path}"


def _get(path: str, **kwargs) -> Any:
    resp = requests.get(_url(path), timeout=_TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, json: dict | None = None, **kwargs) -> Any:
    resp = requests.post(_url(path), json=json, timeout=_TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp.json()


# ─── Health ──────────────────────────────────────────────────────────────── #

def health() -> dict:
    return _get("/api/health")


# ─── Experiments ─────────────────────────────────────────────────────────── #

def list_experiments(limit: int = 50) -> list[dict]:
    return _get("/api/experiments", params={"limit": limit})


def get_experiment(experiment_id: int) -> dict:
    return _get(f"/api/experiments/{experiment_id}")


def get_aggregates(experiment_id: int) -> dict:
    return _get(f"/api/experiments/{experiment_id}/aggregates")


def create_experiment(
    name: str,
    planner_type: str,
    scenario_name: str,
    num_trials: int = 3,
    max_steps: int = 2000,
    headless: bool = True,
    planner_params: dict | None = None,
) -> dict:
    return _post(
        "/api/experiments",
        json={
            "name": name,
            "planner_type": planner_type,
            "scenario_name": scenario_name,
            "num_trials": num_trials,
            "max_steps": max_steps,
            "headless": headless,
            "planner_params": planner_params or {},
        },
    )


# ─── Planning control ─────────────────────────────────────────────────────── #

def run_experiment(experiment_id: int) -> dict:
    return _post(f"/api/experiments/{experiment_id}/run")


def stop_experiment(experiment_id: int) -> dict:
    return _post(f"/api/experiments/{experiment_id}/stop")


def get_sim_status(experiment_id: int) -> dict:
    return _get(f"/api/experiments/{experiment_id}/status")


# ─── Metrics ─────────────────────────────────────────────────────────────── #

def get_metrics(run_id: int) -> list[dict]:
    return _get(f"/api/metrics/{run_id}")


def get_trajectory(run_id: int) -> list[dict]:
    return _get(f"/api/metrics/{run_id}/trajectory")


def get_run_detail(run_id: int) -> dict:
    return _get(f"/api/runs/{run_id}")


# ─── Config ───────────────────────────────────────────────────────────────── #

def list_scenarios() -> list[dict]:
    return _get("/api/config/scenarios")


def list_planners() -> list[dict]:
    return _get("/api/config/planners")
