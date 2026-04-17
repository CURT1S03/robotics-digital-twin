"""Rapidly-exploring Random Tree (RRT) planner.

``plan()`` runs the RRT algorithm to find a collision-free path from
*start* to *goal*, then converts tree nodes to a list of ``Waypoint``\s.

``step()`` uses the same proportional P-controller as ``WaypointPlanner``
to track the RRT-generated path.

The implementation is intentionally straightforward for portfolio clarity.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List

from sim.planners.base_planner import (
    BasePlanner,
    Obstacle,
    Pose2D,
    VelocityCommand,
    Waypoint,
    wrap_angle,
)


# ─── Internal RRT node ──────────────────────────────────────────────────────── #

@dataclass
class _RRTNode:
    x: float
    y: float
    parent: "_RRTNode | None" = None


# ─── Planner ────────────────────────────────────────────────────────────────── #

class RRTPlanner(BasePlanner):
    """RRT path planner with proportional waypoint tracking."""

    def __init__(
        self,
        # RRT parameters
        max_iterations: int = 2000,
        step_size: float = 0.35,       # metres per tree extension
        goal_threshold: float = 0.5,   # goal acceptance radius
        goal_bias: float = 0.10,       # probability of sampling the goal directly
        # Workspace bounds (overridden from scenario)
        bounds: tuple[float, float, float, float] = (-5.0, 15.0, -5.0, 5.0),  # xmin,xmax,ymin,ymax
        # Waypoint tracking (same P-controller as WaypointPlanner)
        arrival_threshold: float = 0.4,
        max_linear_vel: float = 0.8,
        max_angular_vel: float = 1.2,
        kp_angular: float = 2.0,
        slow_zone: float = 1.5,
        # reproducible tests
        seed: int | None = None,
    ) -> None:
        self.max_iterations = max_iterations
        self.step_size = step_size
        self.goal_threshold = goal_threshold
        self.goal_bias = goal_bias
        self.bounds = bounds
        self.arrival_threshold = arrival_threshold
        self.max_linear_vel = max_linear_vel
        self.max_angular_vel = max_angular_vel
        self.kp_angular = kp_angular
        self.slow_zone = slow_zone
        self._rng = random.Random(seed)

        self._waypoints: List[Waypoint] = []
        self._current_idx: int = 0
        self._goal_reached: bool = False
        self._planning_succeeded: bool = False

    # ── BasePlanner interface ──────────────────────────────────────────── #

    @property
    def name(self) -> str:
        return "rrt"

    @property
    def goal_reached(self) -> bool:
        return self._goal_reached

    @property
    def current_path(self) -> List[Waypoint]:
        return list(self._waypoints)

    @property
    def current_waypoint_index(self) -> int:
        return self._current_idx

    @property
    def planning_succeeded(self) -> bool:
        return self._planning_succeeded

    def reset(self) -> None:
        self._waypoints = []
        self._current_idx = 0
        self._goal_reached = False
        self._planning_succeeded = False

    # ── Planning ───────────────────────────────────────────────────────── #

    def plan(
        self,
        start: Pose2D,
        goal: Pose2D,
        obstacles: List[Obstacle],
    ) -> List[Waypoint]:
        """Run RRT and return the planned path as a waypoint list.

        Falls back to a direct path if RRT cannot find a solution within
        *max_iterations*.
        """
        self.reset()

        root = _RRTNode(start.x, start.y)
        nodes: List[_RRTNode] = [root]

        for _ in range(self.max_iterations):
            # Sample
            if self._rng.random() < self.goal_bias:
                rx, ry = goal.x, goal.y
            else:
                rx = self._rng.uniform(self.bounds[0], self.bounds[1])
                ry = self._rng.uniform(self.bounds[2], self.bounds[3])

            # Nearest
            nearest = min(nodes, key=lambda n: (n.x - rx) ** 2 + (n.y - ry) ** 2)

            # Extend
            dx = rx - nearest.x
            dy = ry - nearest.y
            d = math.sqrt(dx ** 2 + dy ** 2)
            if d < 1e-6:
                continue
            new_x = nearest.x + self.step_size * dx / d
            new_y = nearest.y + self.step_size * dy / d
            new_node = _RRTNode(new_x, new_y, parent=nearest)

            # Collision check (straight segment nearest → new)
            if not self._segment_free(nearest, new_node, obstacles):
                continue

            nodes.append(new_node)

            # Goal check
            if math.sqrt((new_node.x - goal.x) ** 2 + (new_node.y - goal.y) ** 2) < self.goal_threshold:
                self._waypoints = self._extract_path(new_node, goal)
                self._planning_succeeded = True
                return self._waypoints

        # Fallback: direct path
        self._waypoints = [Waypoint(goal.x, goal.y)]
        return self._waypoints

    def set_bounds(self, x_min: float, x_max: float, y_min: float, y_max: float) -> None:
        self.bounds = (x_min, x_max, y_min, y_max)

    # ── Tracking ───────────────────────────────────────────────────────── #

    def step(self, current_pose: Pose2D) -> VelocityCommand:
        if self._goal_reached or not self._waypoints:
            return VelocityCommand()

        target = self._waypoints[self._current_idx]
        dx = target.x - current_pose.x
        dy = target.y - current_pose.y
        dist = math.sqrt(dx ** 2 + dy ** 2)

        if dist < self.arrival_threshold:
            if self._current_idx < len(self._waypoints) - 1:
                self._current_idx += 1
                return self.step(current_pose)
            else:
                self._goal_reached = True
                return VelocityCommand()

        desired_heading = math.atan2(dy, dx)
        heading_error = wrap_angle(desired_heading - current_pose.theta)

        align_factor = max(0.0, 1.0 - abs(heading_error) / (math.pi / 2))
        dist_factor = min(1.0, dist / self.slow_zone)
        vx = self.max_linear_vel * align_factor * dist_factor

        omega = self.kp_angular * heading_error
        omega = max(-self.max_angular_vel, min(self.max_angular_vel, omega))

        return VelocityCommand(vx=vx, vy=0.0, omega=omega)

    # ── Internal helpers ───────────────────────────────────────────────── #

    @staticmethod
    def _segment_free(a: _RRTNode, b: _RRTNode, obstacles: List[Obstacle]) -> bool:
        """Return True if the segment a→b is collision-free."""
        n_checks = max(5, int(math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2) / 0.1))
        for i in range(n_checks + 1):
            t = i / n_checks
            px = a.x + t * (b.x - a.x)
            py = a.y + t * (b.y - a.y)
            for obs in obstacles:
                clearance = obs.radius + obs.safety_margin
                if (px - obs.x) ** 2 + (py - obs.y) ** 2 < clearance ** 2:
                    return False
        return True

    @staticmethod
    def _extract_path(leaf: _RRTNode, goal: Pose2D) -> List[Waypoint]:
        """Walk tree from leaf back to root, reverse, and append goal."""
        path: List[Waypoint] = []
        node: _RRTNode | None = leaf
        while node is not None:
            path.append(Waypoint(node.x, node.y))
            node = node.parent
        path.reverse()
        path.append(Waypoint(goal.x, goal.y))
        # Light smoothing: remove collinear intermediate nodes
        return _smooth_path(path)


def _smooth_path(waypoints: List[Waypoint], angle_tol: float = 0.15) -> List[Waypoint]:
    """Remove waypoints where the turn angle is below *angle_tol* radians."""
    if len(waypoints) <= 2:
        return waypoints
    smoothed = [waypoints[0]]
    for i in range(1, len(waypoints) - 1):
        a = smoothed[-1]
        b = waypoints[i]
        c = waypoints[i + 1]
        angle = abs(
            wrap_angle(
                math.atan2(c.y - b.y, c.x - b.x) - math.atan2(b.y - a.y, b.x - a.x)
            )
        )
        if angle > angle_tol:
            smoothed.append(b)
    smoothed.append(waypoints[-1])
    return smoothed
