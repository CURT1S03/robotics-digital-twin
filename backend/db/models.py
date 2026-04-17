"""SQLAlchemy ORM models — Oracle-style naming conventions.

Table and column names are UPPERCASE with underscores, matching Oracle DB
standards.  SQLite type affinities are used at runtime; the comments show
the Oracle DDL equivalent for easy migration.

Tables:
    EXPERIMENTS       — top-level experiment definition
    PLAN_RUNS         — individual trial executions within an experiment
    PERFORMANCE_METRICS — per-trial KPIs persisted after each run
    ROBOT_STATES      — trajectory samples recorded every N sim steps
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENTS
# Oracle DDL:
#   CREATE TABLE EXPERIMENTS (
#       EXPERIMENT_ID   NUMBER(10)      PRIMARY KEY,
#       EXPERIMENT_NAME VARCHAR2(255)   NOT NULL,
#       PLANNER_TYPE    VARCHAR2(64)    NOT NULL,
#       SCENARIO_NAME   VARCHAR2(128)   NOT NULL,
#       STATUS          VARCHAR2(32)    DEFAULT 'queued',
#       CONFIG_JSON     CLOB,
#       LOG_DIR         VARCHAR2(512),
#       CREATED_AT      TIMESTAMP       NOT NULL,
#       FINISHED_AT     TIMESTAMP
#   );
# ─────────────────────────────────────────────────────────────────────────────
class Experiment(Base):
    __tablename__ = "EXPERIMENTS"

    experiment_id: Mapped[int] = mapped_column(
        "EXPERIMENT_ID", Integer, primary_key=True, autoincrement=True
    )
    experiment_name: Mapped[str] = mapped_column("EXPERIMENT_NAME", String(255), nullable=False)
    planner_type: Mapped[str] = mapped_column(
        "PLANNER_TYPE", String(64), nullable=False,
        comment="waypoint | rrt"
    )
    scenario_name: Mapped[str] = mapped_column("SCENARIO_NAME", String(128), nullable=False)
    # status: queued | running | completed | failed | stopped
    status: Mapped[str] = mapped_column("STATUS", String(32), nullable=False, default="queued")
    config_json: Mapped[str] = mapped_column("CONFIG_JSON", Text, nullable=False, default="{}")
    log_dir: Mapped[str | None] = mapped_column("LOG_DIR", String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column("CREATED_AT", DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column("FINISHED_AT", DateTime, nullable=True)

    plan_runs: Mapped[list["PlanRun"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────────────────────
# PLAN_RUNS
# Oracle DDL:
#   CREATE TABLE PLAN_RUNS (
#       RUN_ID          NUMBER(10)      PRIMARY KEY,
#       EXPERIMENT_ID   NUMBER(10)      REFERENCES EXPERIMENTS(EXPERIMENT_ID),
#       TRIAL_NUMBER    NUMBER(5)       NOT NULL,
#       STATUS          VARCHAR2(32)    DEFAULT 'queued',
#       GOAL_REACHED    NUMBER(1)       DEFAULT 0,
#       START_TIME      TIMESTAMP,
#       END_TIME        TIMESTAMP
#   );
# ─────────────────────────────────────────────────────────────────────────────
class PlanRun(Base):
    __tablename__ = "PLAN_RUNS"

    run_id: Mapped[int] = mapped_column(
        "RUN_ID", Integer, primary_key=True, autoincrement=True
    )
    experiment_id: Mapped[int] = mapped_column(
        "EXPERIMENT_ID", Integer, ForeignKey("EXPERIMENTS.EXPERIMENT_ID"), nullable=False
    )
    trial_number: Mapped[int] = mapped_column("TRIAL_NUMBER", Integer, nullable=False, default=1)
    # status: queued | running | completed | failed
    status: Mapped[str] = mapped_column("STATUS", String(32), nullable=False, default="queued")
    goal_reached: Mapped[bool] = mapped_column("GOAL_REACHED", Boolean, nullable=False, default=False)
    start_time: Mapped[datetime | None] = mapped_column("START_TIME", DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column("END_TIME", DateTime, nullable=True)

    experiment: Mapped["Experiment"] = relationship(back_populates="plan_runs")
    metrics: Mapped[list["PerformanceMetric"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    robot_states: Mapped[list["RobotState"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────────────────────
# PERFORMANCE_METRICS
# Oracle DDL:
#   CREATE TABLE PERFORMANCE_METRICS (
#       METRIC_ID       NUMBER(10)      PRIMARY KEY,
#       RUN_ID          NUMBER(10)      REFERENCES PLAN_RUNS(RUN_ID),
#       METRIC_NAME     VARCHAR2(64)    NOT NULL,
#       METRIC_VALUE    FLOAT           NOT NULL,
#       RECORDED_AT     TIMESTAMP       NOT NULL
#   );
# ─────────────────────────────────────────────────────────────────────────────
class PerformanceMetric(Base):
    __tablename__ = "PERFORMANCE_METRICS"

    metric_id: Mapped[int] = mapped_column(
        "METRIC_ID", Integer, primary_key=True, autoincrement=True
    )
    run_id: Mapped[int] = mapped_column(
        "RUN_ID", Integer, ForeignKey("PLAN_RUNS.RUN_ID"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(
        "METRIC_NAME", String(64), nullable=False,
        comment="path_length | energy | collision_count | completion_time | tracking_error"
    )
    metric_value: Mapped[float] = mapped_column("METRIC_VALUE", Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        "RECORDED_AT", DateTime, default=datetime.utcnow
    )

    run: Mapped["PlanRun"] = relationship(back_populates="metrics")


# ─────────────────────────────────────────────────────────────────────────────
# ROBOT_STATES  (trajectory samples)
# Oracle DDL:
#   CREATE TABLE ROBOT_STATES (
#       STATE_ID        NUMBER(10)      PRIMARY KEY,
#       RUN_ID          NUMBER(10)      REFERENCES PLAN_RUNS(RUN_ID),
#       SIM_STEP        NUMBER(10)      NOT NULL,
#       POSITION_X      FLOAT           NOT NULL,
#       POSITION_Y      FLOAT           NOT NULL,
#       ORIENTATION     FLOAT           NOT NULL,
#       LINEAR_VEL      FLOAT           NOT NULL,
#       ANGULAR_VEL     FLOAT           NOT NULL,
#       RECORDED_AT     TIMESTAMP       NOT NULL
#   );
# ─────────────────────────────────────────────────────────────────────────────
class RobotState(Base):
    __tablename__ = "ROBOT_STATES"

    state_id: Mapped[int] = mapped_column(
        "STATE_ID", Integer, primary_key=True, autoincrement=True
    )
    run_id: Mapped[int] = mapped_column(
        "RUN_ID", Integer, ForeignKey("PLAN_RUNS.RUN_ID"), nullable=False
    )
    sim_step: Mapped[int] = mapped_column("SIM_STEP", Integer, nullable=False)
    position_x: Mapped[float] = mapped_column("POSITION_X", Float, nullable=False)
    position_y: Mapped[float] = mapped_column("POSITION_Y", Float, nullable=False)
    orientation: Mapped[float] = mapped_column("ORIENTATION", Float, nullable=False)
    linear_vel: Mapped[float] = mapped_column("LINEAR_VEL", Float, nullable=False)
    angular_vel: Mapped[float] = mapped_column("ANGULAR_VEL", Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        "RECORDED_AT", DateTime, default=datetime.utcnow
    )

    run: Mapped["PlanRun"] = relationship(back_populates="robot_states")
