"""Mock ROS 2 message types.

Mirrors common ROS 2 message structures:
  - ``OdometryMsg``     → nav_msgs/Odometry
  - ``PlanStatusMsg``   → custom planning status
  - ``PerformanceMetricsMsg`` → custom end-of-trial summary
  - ``VelocityCommandMsg``    → geometry_msgs/Twist
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Header:
    """Mimics std_msgs/Header."""

    stamp: datetime = field(default_factory=datetime.utcnow)
    frame_id: str = "world"


@dataclass
class OdometryMsg:
    """Robot pose and velocity in the world frame.

    Mirrors nav_msgs/Odometry (simplified — no covariance).
    """

    header: Header = field(default_factory=Header)
    # Pose
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    yaw: float = 0.0  # radians
    # Twist
    linear_x: float = 0.0
    linear_y: float = 0.0
    angular_z: float = 0.0
    # Metadata
    run_id: int = 0
    step: int = 0


@dataclass
class PlanStatusMsg:
    """Real-time status from the active planning algorithm.

    Published every simulation step while an experiment is running.
    """

    header: Header = field(default_factory=Header)
    run_id: int = 0
    planner_type: str = ""
    # Waypoint progress
    current_waypoint_idx: int = 0
    total_waypoints: int = 0
    distance_to_goal: float = 0.0
    heading_error: float = 0.0  # radians
    # Status: "planning" | "executing" | "reached" | "failed"
    status: str = "planning"
    step: int = 0


@dataclass
class PerformanceMetricsMsg:
    """Aggregated metrics published once at the end of each trial.

    These are persisted to the PERFORMANCE_METRICS table.
    """

    header: Header = field(default_factory=Header)
    run_id: int = 0
    planner_type: str = ""
    scenario_name: str = ""
    # Navigation metrics
    path_length: float = 0.0          # metres travelled
    energy_consumed: float = 0.0      # sum of |velocity| over time (proxy)
    collision_count: int = 0
    completion_time: float = 0.0      # seconds of sim time
    goal_reached: bool = False
    mean_tracking_error: float = 0.0  # mean deviation from planned path (m)
    total_steps: int = 0


@dataclass
class VelocityCommandMsg:
    """Velocity command sent to the robot.

    Mirrors geometry_msgs/Twist (linear + angular).
    """

    header: Header = field(default_factory=Header)
    linear_x: float = 0.0   # forward velocity  (m/s)
    linear_y: float = 0.0   # lateral velocity  (m/s)
    angular_z: float = 0.0  # yaw rate          (rad/s)
