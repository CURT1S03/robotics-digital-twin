"""Common data structures and abstract base class for planning algorithms.

All planners must implement:
    plan(start, goal, obstacles) -> List[Waypoint]
    step(current_pose) -> VelocityCommand
    reset() -> None
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


# ─── Primitive types ────────────────────────────────────────────────────────── #

@dataclass
class Pose2D:
    """Robot pose in the world frame."""

    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0  # yaw in radians

    def distance_to(self, other: "Pose2D") -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)


@dataclass
class Waypoint:
    """A 2-D navigation waypoint."""

    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0  # desired heading at this waypoint (radians, optional)

    def as_pose(self) -> Pose2D:
        return Pose2D(self.x, self.y, self.heading)


@dataclass
class Obstacle:
    """Circular obstacle in the 2-D planning space."""

    x: float = 0.0
    y: float = 0.0
    radius: float = 0.5        # metres
    safety_margin: float = 0.3 # extra clearance around the physical radius


@dataclass
class VelocityCommand:
    """Velocity command sent to the robot locomotion controller."""

    vx: float = 0.0     # forward velocity (m/s)
    vy: float = 0.0     # lateral velocity (m/s) — kept 0 for non-holonomic
    omega: float = 0.0  # yaw rate (rad/s)


# ─── Utility ────────────────────────────────────────────────────────────────── #

def wrap_angle(angle: float) -> float:
    """Wrap *angle* to the range (-π, π]."""
    return (angle + math.pi) % (2 * math.pi) - math.pi


# ─── Abstract planner ───────────────────────────────────────────────────────── #

class BasePlanner(ABC):
    """Abstract interface that all planning algorithms must satisfy."""

    # ── Planning ───────────────────────────────────────────────────────── #

    @abstractmethod
    def plan(
        self,
        start: Pose2D,
        goal: Pose2D,
        obstacles: List[Obstacle],
    ) -> List[Waypoint]:
        """Compute a path from *start* to *goal* avoiding *obstacles*.

        Must populate internal state consumed by ``step()``.
        Returns the planned waypoint list (may be empty on failure).
        """
        ...

    @abstractmethod
    def step(self, current_pose: Pose2D) -> VelocityCommand:
        """Return a velocity command to advance the robot along the planned path."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Clear all internal planner state."""
        ...

    # ── Introspection ──────────────────────────────────────────────────── #

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique planner identifier (snake_case)."""
        ...

    @property
    def goal_reached(self) -> bool:
        return False

    @property
    def current_path(self) -> List[Waypoint]:
        return []

    @property
    def current_waypoint_index(self) -> int:
        return 0
