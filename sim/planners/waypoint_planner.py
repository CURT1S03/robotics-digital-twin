"""Waypoint-following planner with proportional velocity control.

Behaviour:
    ``plan()`` — stores the provided waypoints (plus the goal) as the path.
    ``step()`` — computes a (vx, omega) command to steer toward the current
                 target waypoint using a P-controller on heading error,
                 then advances to the next waypoint once within
                 *arrival_threshold*.

This planner performs *no* obstacle avoidance — it drives straight between
waypoints.  It is the simplest possible baseline for comparison against RRT.
"""

from __future__ import annotations

import math
from typing import List

from sim.planners.base_planner import (
    BasePlanner,
    Obstacle,
    Pose2D,
    VelocityCommand,
    Waypoint,
    wrap_angle,
)


class WaypointPlanner(BasePlanner):
    """Proportional P-controller waypoint follower."""

    def __init__(
        self,
        arrival_threshold: float = 0.35,  # metres — distance to switch waypoint
        max_linear_vel: float = 0.8,       # m/s
        max_angular_vel: float = 1.2,      # rad/s
        kp_angular: float = 2.0,           # proportional gain on heading error
        slow_zone: float = 1.5,            # reduce speed within this radius of goal
    ) -> None:
        self.arrival_threshold = arrival_threshold
        self.max_linear_vel = max_linear_vel
        self.max_angular_vel = max_angular_vel
        self.kp_angular = kp_angular
        self.slow_zone = slow_zone

        self._waypoints: List[Waypoint] = []
        self._current_idx: int = 0
        self._goal_reached: bool = False

    # ── BasePlanner interface ──────────────────────────────────────────── #

    @property
    def name(self) -> str:
        return "waypoint"

    @property
    def goal_reached(self) -> bool:
        return self._goal_reached

    @property
    def current_path(self) -> List[Waypoint]:
        return list(self._waypoints)

    @property
    def current_waypoint_index(self) -> int:
        return self._current_idx

    def reset(self) -> None:
        self._waypoints = []
        self._current_idx = 0
        self._goal_reached = False

    def plan(
        self,
        start: Pose2D,
        goal: Pose2D,
        obstacles: List[Obstacle],
    ) -> List[Waypoint]:
        """Accept provided waypoints and append *goal* as the final target.

        Obstacles are ignored (no avoidance).
        """
        self.reset()
        self._waypoints = []
        # If callers pass scenario waypoints include them; otherwise direct goal
        self._waypoints.append(Waypoint(goal.x, goal.y))
        return self._waypoints

    def plan_with_waypoints(
        self,
        start: Pose2D,
        waypoints: List[Waypoint],
        obstacles: List[Obstacle],
    ) -> List[Waypoint]:
        """Use explicit waypoints (from scenario YAML) as the path."""
        self.reset()
        self._waypoints = list(waypoints)
        return self._waypoints

    def step(self, current_pose: Pose2D) -> VelocityCommand:
        if self._goal_reached or not self._waypoints:
            return VelocityCommand()

        target = self._waypoints[self._current_idx]
        dx = target.x - current_pose.x
        dy = target.y - current_pose.y
        dist = math.sqrt(dx ** 2 + dy ** 2)

        # Advance to next waypoint?
        if dist < self.arrival_threshold:
            if self._current_idx < len(self._waypoints) - 1:
                self._current_idx += 1
                return self.step(current_pose)   # recurse to new target
            else:
                self._goal_reached = True
                return VelocityCommand()

        # Heading error
        desired_heading = math.atan2(dy, dx)
        heading_error = wrap_angle(desired_heading - current_pose.theta)

        # Scale forward speed: slow near goal, slow when misaligned
        align_factor = max(0.0, 1.0 - abs(heading_error) / (math.pi / 2))
        dist_factor = min(1.0, dist / self.slow_zone)
        vx = self.max_linear_vel * align_factor * dist_factor

        omega = self.kp_angular * heading_error
        omega = max(-self.max_angular_vel, min(self.max_angular_vel, omega))

        return VelocityCommand(vx=vx, vy=0.0, omega=omega)
