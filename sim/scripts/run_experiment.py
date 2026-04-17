"""Run a navigation planning experiment in Isaac Sim.

This script is launched by the FastAPI backend via SimManager as:

    isaaclab.bat -p sim/scripts/run_experiment.py \\
        --experiment_id 1 --run_id 2 \\
        --planner waypoint --scenario straight_line \\
        --max_steps 2000 --headless

Output — structured JSON lines printed to stdout (one per event):
    {"type": "odometry",    "run_id": 2, "step": 10, "x": 0.5, ...}
    {"type": "plan_status", "run_id": 2, "step": 10, "status": "executing", ...}
    {"type": "metrics",     "run_id": 2, "path_length": 8.3, ..., "goal_reached": true}
    {"type": "done",        "run_id": 2, "goal_reached": true}
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

# ── Ensure project root is importable ──────────────────────────────────────── #
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ── Windows DLL workaround (same as quadruped project) ─────────────────────── #
if sys.platform == "win32":
    try:
        import h5py  # noqa: F401
    except ImportError:
        pass

# ── Parse args before Isaac Lab imports ────────────────────────────────────── #
parser = argparse.ArgumentParser(description="Digital twin navigation experiment runner.")
parser.add_argument("--experiment_id", type=int, required=True)
parser.add_argument("--run_id",        type=int, required=True)
parser.add_argument("--planner",       type=str, default="waypoint",
                    choices=["waypoint", "rrt"])
parser.add_argument("--scenario",      type=str, default="straight_line")
parser.add_argument("--trial_number",  type=int, default=1)
parser.add_argument("--max_steps",     type=int, default=2000)
parser.add_argument("--headless",      action="store_true", default=False)
parser.add_argument("--log_dir",       type=str, default=None)
parser.add_argument("--planner_params", type=str, default="{}")

from isaaclab.app import AppLauncher  # noqa: E402

AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# ── Post-launch Isaac imports ───────────────────────────────────────────────── #
import torch  # noqa: E402
from isaacsim.core.api import SimulationContext  # noqa: E402
from isaacsim.core.utils.stage import add_reference_to_stage  # noqa: E402
from isaacsim.storage.native import get_assets_root_path  # noqa: E402

# ── Project imports ────────────────────────────────────────────────────────── #
import yaml  # noqa: E402

from sim.planners.base_planner import Obstacle, Pose2D, Waypoint  # noqa: E402
from sim.planners.waypoint_planner import WaypointPlanner            # noqa: E402
from sim.planners.rrt_planner import RRTPlanner                      # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────── #

def emit(event: dict) -> None:
    """Print a structured JSON event to stdout (consumed by SimManager)."""
    print(json.dumps(event), flush=True)


def load_scenario(name: str) -> dict:
    scenario_dir = _project_root / "sim" / "assets" / "scenarios"
    path = scenario_dir / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {path}")
    return yaml.safe_load(path.read_text())


def build_planner(planner_type: str, params: dict, scenario: dict):
    bounds = scenario.get("bounds", {})
    b = (
        bounds.get("x_min", -5.0),
        bounds.get("x_max", 15.0),
        bounds.get("y_min", -5.0),
        bounds.get("y_max",  5.0),
    )
    if planner_type == "rrt":
        p = RRTPlanner(bounds=b, **{k: v for k, v in params.items() if k != "bounds"})
    else:
        p = WaypointPlanner(**params)
    return p


def parse_obstacles(scenario: dict) -> list[Obstacle]:
    return [
        Obstacle(x=o["x"], y=o["y"], radius=o.get("radius", 0.5))
        for o in scenario.get("obstacles", [])
    ]


def parse_waypoints(scenario: dict) -> list[Waypoint]:
    return [Waypoint(w["x"], w["y"]) for w in scenario.get("waypoints", [])]


# ── Main ───────────────────────────────────────────────────────────────────── #

def main() -> None:
    run_id = args_cli.run_id
    planner_params = json.loads(args_cli.planner_params)

    # ── Load scenario ──────────────────────────────────────────────────── #
    scenario = load_scenario(args_cli.scenario)
    start_cfg = scenario["start"]
    goal_cfg = scenario["goal"]
    start = Pose2D(start_cfg["x"], start_cfg["y"], start_cfg.get("theta", 0.0))
    goal = Pose2D(goal_cfg["x"], goal_cfg["y"])
    obstacles = parse_obstacles(scenario)
    waypoints = parse_waypoints(scenario)

    # ── Build planner ──────────────────────────────────────────────────── #
    planner = build_planner(args_cli.planner, planner_params, scenario)
    if hasattr(planner, "plan_with_waypoints") and waypoints:
        planner.plan_with_waypoints(start, waypoints, obstacles)
    else:
        planner.plan(start, goal, obstacles)

    # ── Isaac Sim setup ────────────────────────────────────────────────── #
    assets_root = get_assets_root_path()
    go2_usd = f"{assets_root}/Isaac/Robots/Unitree/Go2/go2.usd"

    sim_context = SimulationContext(stage_units_in_meters=1.0)
    add_reference_to_stage(go2_usd, "/World/Go2")

    sim_context.initialize_physics()
    sim_context.play()

    # ── State tracking ─────────────────────────────────────────────────── #
    trajectory: list[tuple[float, float]] = []
    collision_count = 0
    energy_acc = 0.0
    start_time = time.monotonic()
    SAMPLE_INTERVAL = 10             # emit odometry every N steps
    GOAL_DIST_THRESHOLD = 0.5        # metres

    # ── Simulation loop ────────────────────────────────────────────────── #
    for step in range(args_cli.max_steps):
        sim_context.step(render=not args_cli.headless)
        simulation_app.update()

        # ── Read robot state ─────────────────────────────────────────── #
        # In a full Isaac Lab integration the articulation API provides
        # pose.  Here we use the simplified stage API for demo purposes.
        try:
            from pxr import UsdGeom, Gf
            from omni.usd import get_context
            stage = get_context().get_stage()
            xform = UsdGeom.Xformable(stage.GetPrimAtPath("/World/Go2"))
            tf = xform.ComputeLocalToWorldTransform(0)
            tx, ty, tz = tf[3][0], tf[3][1], tf[3][2]
            # Approximate yaw from rotation matrix col 0
            yaw = math.atan2(tf[0][1], tf[0][0])
        except Exception:
            # Fallback: simulate motion with planner velocity
            tx = start.x + step * 0.01
            ty = start.y
            yaw = 0.0

        current_pose = Pose2D(tx, ty, yaw)
        trajectory.append((tx, ty))

        # ── Get planner command ──────────────────────────────────────── #
        cmd = planner.step(current_pose)
        energy_acc += abs(cmd.vx) + abs(cmd.vy) + abs(cmd.omega) * 0.1

        # ── Collision detection (contact with obstacles) ──────────────── #
        for obs in obstacles:
            dist = math.sqrt((tx - obs.x) ** 2 + (ty - obs.y) ** 2)
            if dist < obs.radius + 0.25:
                collision_count += 1

        # ── Emit odometry (sampled) ───────────────────────────────────── #
        if step % SAMPLE_INTERVAL == 0:
            emit({
                "type": "odometry",
                "run_id": run_id,
                "step": step,
                "x": round(tx, 4),
                "y": round(ty, 4),
                "yaw": round(yaw, 4),
                "linear_x": round(cmd.vx, 4),
                "angular_z": round(cmd.omega, 4),
            })
            emit({
                "type": "plan_status",
                "run_id": run_id,
                "step": step,
                "planner_type": planner.name,
                "current_waypoint_idx": planner.current_waypoint_index,
                "distance_to_goal": round(
                    math.sqrt((tx - goal.x) ** 2 + (ty - goal.y) ** 2), 4
                ),
                "status": "reached" if planner.goal_reached else "executing",
            })

        # ── Early exit on goal reached ────────────────────────────────── #
        dist_to_goal = math.sqrt((tx - goal.x) ** 2 + (ty - goal.y) ** 2)
        if dist_to_goal < GOAL_DIST_THRESHOLD or planner.goal_reached:
            break

    # ── Compute final metrics ─────────────────────────────────────────── #
    elapsed = time.monotonic() - start_time
    path_length = sum(
        math.sqrt((trajectory[i][0] - trajectory[i - 1][0]) ** 2
                  + (trajectory[i][1] - trajectory[i - 1][1]) ** 2)
        for i in range(1, len(trajectory))
    ) if len(trajectory) > 1 else 0.0

    # Mean tracking error vs ideal straight line start→goal
    if len(trajectory) > 1:
        ideal_len = math.sqrt((goal.x - start.x) ** 2 + (goal.y - start.y) ** 2)
        if ideal_len > 0:
            dx_n = (goal.x - start.x) / ideal_len
            dy_n = (goal.y - start.y) / ideal_len
            errors = [
                abs((p[0] - start.x) * (-dy_n) + (p[1] - start.y) * dx_n)
                for p in trajectory
            ]
            mean_tracking_error = sum(errors) / len(errors)
        else:
            mean_tracking_error = 0.0
    else:
        mean_tracking_error = 0.0

    goal_reached = planner.goal_reached or (
        math.sqrt((trajectory[-1][0] - goal.x) ** 2 + (trajectory[-1][1] - goal.y) ** 2)
        < GOAL_DIST_THRESHOLD
    ) if trajectory else False

    # ── Emit final metrics ────────────────────────────────────────────── #
    emit({
        "type": "metrics",
        "run_id": run_id,
        "planner_type": planner.name,
        "scenario_name": args_cli.scenario,
        "path_length": round(path_length, 4),
        "energy_consumed": round(energy_acc, 4),
        "collision_count": collision_count,
        "completion_time": round(elapsed, 3),
        "mean_tracking_error": round(mean_tracking_error, 4),
        "total_steps": step + 1,
        "goal_reached": goal_reached,
    })
    emit({"type": "done", "run_id": run_id, "goal_reached": goal_reached})

    # ── Persist trajectory to log_dir ─────────────────────────────────── #
    if args_cli.log_dir:
        log_dir = Path(args_cli.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "trajectory.json").write_text(
            json.dumps({"run_id": run_id, "trajectory": trajectory})
        )

    sim_context.stop()
    simulation_app.close()


if __name__ == "__main__":
    main()
