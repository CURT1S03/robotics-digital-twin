"""Offline validation tool — runs all planners against all scenarios without Isaac Sim.

Usage:
    python sim/scripts/validate_plan.py
    python sim/scripts/validate_plan.py --planner rrt --scenario obstacle_course

Runs the planner in a lightweight 2-D Python simulation (no Isaac Sim required)
and prints a comparison table.  Useful for rapid algorithm iteration.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import yaml

_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))

from sim.planners.base_planner import Obstacle, Pose2D, Waypoint
from sim.planners.waypoint_planner import WaypointPlanner
from sim.planners.rrt_planner import RRTPlanner


# ── 2-D kinematic simulation ───────────────────────────────────────────────── #

def step_kinematics(pose: Pose2D, vx: float, vy: float, omega: float, dt: float = 0.05) -> Pose2D:
    """Integrate a simple unicycle-model for one timestep."""
    new_x = pose.x + vx * math.cos(pose.theta) * dt - vy * math.sin(pose.theta) * dt
    new_y = pose.y + vx * math.sin(pose.theta) * dt + vy * math.cos(pose.theta) * dt
    new_theta = pose.theta + omega * dt
    return Pose2D(new_x, new_y, new_theta)


def run_scenario_offline(planner, scenario: dict, max_steps: int = 2000, dt: float = 0.05) -> dict:
    """Simulate *planner* on *scenario* using 2-D kinematics (no Isaac Sim)."""
    start_cfg = scenario["start"]
    goal_cfg = scenario["goal"]
    start = Pose2D(start_cfg["x"], start_cfg["y"], start_cfg.get("theta", 0.0))
    goal = Pose2D(goal_cfg["x"], goal_cfg["y"])
    obstacles = [
        Obstacle(x=o["x"], y=o["y"], radius=o.get("radius", 0.5))
        for o in scenario.get("obstacles", [])
    ]
    waypoints = [Waypoint(w["x"], w["y"]) for w in scenario.get("waypoints", [])]

    planner.reset()
    if hasattr(planner, "plan_with_waypoints") and waypoints:
        planner.plan_with_waypoints(start, waypoints, obstacles)
    else:
        planner.plan(start, goal, obstacles)

    pose = Pose2D(start.x, start.y, start.theta)
    trajectory = [(pose.x, pose.y)]
    collision_count = 0
    energy_acc = 0.0
    t_start = time.monotonic()
    GOAL_THR = 0.5

    for step in range(max_steps):
        cmd = planner.step(pose)
        energy_acc += abs(cmd.vx) + abs(cmd.omega) * 0.1
        pose = step_kinematics(pose, cmd.vx, cmd.vy, cmd.omega, dt)
        trajectory.append((pose.x, pose.y))

        for obs in obstacles:
            if math.sqrt((pose.x - obs.x) ** 2 + (pose.y - obs.y) ** 2) < obs.radius + 0.2:
                collision_count += 1

        if math.sqrt((pose.x - goal.x) ** 2 + (pose.y - goal.y) ** 2) < GOAL_THR:
            break

    elapsed = time.monotonic() - t_start
    path_len = sum(
        math.sqrt((trajectory[i][0] - trajectory[i-1][0])**2 + (trajectory[i][1] - trajectory[i-1][1])**2)
        for i in range(1, len(trajectory))
    )
    goal_reached = math.sqrt((pose.x - goal.x)**2 + (pose.y - goal.y)**2) < GOAL_THR

    return {
        "planner": planner.name,
        "scenario": scenario.get("description", ""),
        "goal_reached": goal_reached,
        "path_length": round(path_len, 3),
        "energy": round(energy_acc, 3),
        "collisions": collision_count,
        "steps": step + 1,
        "wall_time_ms": round((elapsed) * 1000, 1),
    }


# ── CLI ────────────────────────────────────────────────────────────────────── #

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--planner", choices=["waypoint", "rrt", "all"], default="all")
    parser.add_argument("--scenario", default="all")
    parser.add_argument("--max_steps", type=int, default=2000)
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
    args = parser.parse_args()

    scenario_dir = _project_root / "sim" / "assets" / "scenarios"
    if args.scenario == "all":
        scenario_files = sorted(scenario_dir.glob("*.yaml"))
    else:
        scenario_files = [scenario_dir / f"{args.scenario}.yaml"]

    planners_to_run = []
    if args.planner in ("waypoint", "all"):
        planners_to_run.append(WaypointPlanner())
    if args.planner in ("rrt", "all"):
        planners_to_run.append(RRTPlanner(seed=42))

    results = []
    for sf in scenario_files:
        scenario = yaml.safe_load(sf.read_text())
        for planner in planners_to_run:
            r = run_scenario_offline(planner, scenario, max_steps=args.max_steps)
            r["scenario_file"] = sf.stem
            results.append(r)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    # Print table
    header = f"{'Planner':<12} {'Scenario':<20} {'Reached':>7} {'Path(m)':>9} {'Energy':>8} {'Coll.':>6} {'Steps':>6} {'ms':>8}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['planner']:<12} {r['scenario_file']:<20} "
            f"{'✓' if r['goal_reached'] else '✗':>7} "
            f"{r['path_length']:>9.3f} {r['energy']:>8.3f} "
            f"{r['collisions']:>6} {r['steps']:>6} {r['wall_time_ms']:>8.1f}"
        )


if __name__ == "__main__":
    main()
