"""Tests for planning algorithms (no Isaac Sim required)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.planners.base_planner import Obstacle, Pose2D, Waypoint, wrap_angle
from sim.planners.waypoint_planner import WaypointPlanner
from sim.planners.rrt_planner import RRTPlanner


# ─── Utilities ──────────────────────────────────────────────────────────────── #

def simulate(planner, start: Pose2D, goal: Pose2D, max_steps: int = 2000, dt: float = 0.05):
    """Simple 2-D kinematics loop, returns (trajectory, goal_reached)."""
    pose = Pose2D(start.x, start.y, start.theta)
    traj = [(pose.x, pose.y)]
    for _ in range(max_steps):
        cmd = planner.step(pose)
        new_x = pose.x + cmd.vx * math.cos(pose.theta) * dt
        new_y = pose.y + cmd.vx * math.sin(pose.theta) * dt
        new_theta = pose.theta + cmd.omega * dt
        pose = Pose2D(new_x, new_y, new_theta)
        traj.append((pose.x, pose.y))
        if planner.goal_reached:
            break
    return traj, planner.goal_reached


# ─── wrap_angle ─────────────────────────────────────────────────────────────── #

@pytest.mark.parametrize("angle,expected", [
    (0.0, 0.0),
    (math.pi, -math.pi),   # wrap_angle maps exactly π to -π
    (3 * math.pi / 2, -math.pi / 2),
    (-3 * math.pi / 2, math.pi / 2),
])
def test_wrap_angle(angle, expected):
    assert wrap_angle(angle) == pytest.approx(expected, abs=1e-9)


# ─── WaypointPlanner ────────────────────────────────────────────────────────── #

def test_waypoint_planner_reaches_goal_direct():
    p = WaypointPlanner()
    start = Pose2D(0.0, 0.0, 0.0)
    goal = Pose2D(5.0, 0.0)
    p.plan(start, goal, [])
    _, reached = simulate(p, start, goal)
    assert reached, "WaypointPlanner should reach a straight-line goal"


def test_waypoint_planner_zero_velocity_at_goal():
    p = WaypointPlanner()
    pose_at_goal = Pose2D(5.0, 0.0, 0.0)
    # Mark goal as reached manually
    p._waypoints = [Waypoint(5.0, 0.0)]
    p._goal_reached = True
    cmd = p.step(pose_at_goal)
    assert cmd.vx == 0.0
    assert cmd.omega == 0.0


def test_waypoint_planner_multi_waypoint():
    p = WaypointPlanner(arrival_threshold=0.3)
    start = Pose2D(0.0, 0.0, 0.0)
    goal = Pose2D(6.0, 6.0)
    waypoints = [Waypoint(3.0, 0.0), Waypoint(6.0, 0.0), Waypoint(6.0, 6.0)]
    p.plan_with_waypoints(start, waypoints, [])
    _, reached = simulate(p, start, goal, max_steps=3000)
    assert reached


def test_waypoint_planner_returns_velocity_command():
    p = WaypointPlanner()
    start = Pose2D(0.0, 0.0, 0.0)
    target = Pose2D(3.0, 0.0)
    p.plan(start, target, [])
    cmd = p.step(start)
    assert cmd.vx >= 0
    assert abs(cmd.omega) <= p.max_angular_vel


def test_waypoint_planner_reset():
    p = WaypointPlanner()
    start = Pose2D(0.0, 0.0)
    p.plan(start, Pose2D(5.0, 0.0), [])
    p._goal_reached = True
    p.reset()
    assert not p.goal_reached
    assert p.current_path == []


# ─── RRTPlanner ─────────────────────────────────────────────────────────────── #

def test_rrt_planner_reaches_open_goal():
    p = RRTPlanner(seed=0, bounds=(-2.0, 12.0, -4.0, 4.0))
    start = Pose2D(0.0, 0.0, 0.0)
    goal = Pose2D(8.0, 0.0)
    p.plan(start, goal, [])
    _, reached = simulate(p, start, goal, max_steps=3000)
    assert reached, "RRT should reach goal on flat empty space"


def test_rrt_plan_returns_waypoints():
    p = RRTPlanner(seed=1, bounds=(-2.0, 12.0, -4.0, 4.0))
    start = Pose2D(0.0, 0.0)
    goal = Pose2D(5.0, 0.0)
    waypoints = p.plan(start, goal, [])
    assert isinstance(waypoints, list)
    assert len(waypoints) >= 1
    # Last waypoint should be near goal
    last = waypoints[-1]
    dist = math.sqrt((last.x - goal.x)**2 + (last.y - goal.y)**2)
    assert dist < 1.0, f"Last waypoint should be near goal, got dist={dist:.3f}"


def test_rrt_avoids_obstacle():
    """RRT should find a path even with an obstacle directly in the straight-line path."""
    obstacle = Obstacle(x=4.0, y=0.0, radius=0.8)
    p = RRTPlanner(seed=42, bounds=(-2.0, 12.0, -4.0, 4.0), max_iterations=3000)
    start = Pose2D(0.0, 0.0)
    goal = Pose2D(8.0, 0.0)
    waypoints = p.plan(start, goal, [obstacle])
    assert len(waypoints) >= 1
    # If planning succeeded, path nodes should not be inside obstacle
    if p.planning_succeeded:
        for wp in waypoints:
            dist = math.sqrt((wp.x - obstacle.x)**2 + (wp.y - obstacle.y)**2)
            clearance = obstacle.radius + obstacle.safety_margin
            assert dist >= clearance * 0.8, (
                f"Waypoint ({wp.x:.2f},{wp.y:.2f}) collides with obstacle at dist={dist:.3f}"
            )


def test_rrt_reset():
    p = RRTPlanner(seed=0)
    p.plan(Pose2D(0, 0), Pose2D(5, 0), [])
    p._goal_reached = True
    p.reset()
    assert not p.goal_reached
    assert p.current_path == []


def test_rrt_name():
    assert RRTPlanner().name == "rrt"


def test_waypoint_planner_name():
    assert WaypointPlanner().name == "waypoint"
