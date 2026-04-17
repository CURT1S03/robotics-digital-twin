# Robotics Digital Twin

A portfolio-quality full-stack application demonstrating a **digital twin workflow** for the Unitree Go2 quadruped robot. Navigation planners are evaluated inside NVIDIA Isaac Sim, experiment results are stored in a relational database, and live telemetry is visualised through a Streamlit dashboard.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  NVIDIA Isaac Sim / Isaac Lab                                            │
│  sim/scripts/run_experiment.py                                           │
│   • Loads Go2 USD from Nucleus                                           │
│   • Runs planner (Waypoint or RRT) in sim loop                          │
│   • Emits structured JSON events to stdout                               │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │ stdout JSON lines
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FastAPI Backend  (port 8000)                                            │
│   SimManager ──► reads subprocess stdout                                 │
│   ROSBridgeService ──► persists events to DB, fans out to WebSocket       │
│   Mock ROS 2 layer ──► asyncio pub/sub (no ROS install needed)           │
│   SQLAlchemy async ──► SQLite (Oracle-style schema)                      │
│   REST API + WebSocket /ws/telemetry                                     │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │ HTTP / WebSocket
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Streamlit Dashboard  (port 8501)                                        │
│   Experiments page  ──► create / run / stop experiments                  │
│   Comparison page   ──► cross-planner metric charts                      │
│   Live Monitor page ──► 2-s polling telemetry during active runs         │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| NVIDIA Isaac Sim | 5.1.0 |
| Isaac Lab | 2.7.0 |
| Conda environment | `env_isaaclab` (Python 3.10) |
| Python (standalone) | 3.11+ (for offline planner tests) |

Python packages are declared in `requirements.txt`. Install them inside the project's virtual environment (or the conda env):

```bash
conda activate env_isaaclab
pip install -r requirements.txt
```

---

## Quick Start

### 1 — Configure paths

Copy `.env.example` to `.env` and edit the paths to match your installation:

```bash
cp .env.example .env
```

Key variables:

```
ISAACSIM_PATH=A:/Projects/IsaacSim/isaac-sim-standalone-5.1.0-windows-x86_64
ISAACLAB_PATH=A:/Projects/IsaacLab
CONDA_ENV_NAME=env_isaaclab
DATABASE_URL=sqlite+aiosqlite:///logs/digital_twin.db
```

### 2 — Start the backend

```bash
cd a:\Projects\DigitalTwin\robotics-digital-twin
conda activate env_isaaclab
uvicorn backend.main:app --reload --port 8000
```

API docs are available at <http://localhost:8000/docs>.

### 3 — Start the dashboard

Open a second terminal:

```bash
cd a:\Projects\DigitalTwin\robotics-digital-twin
conda activate env_isaaclab
streamlit run dashboard/app.py --server.port 8501
```

Navigate to <http://localhost:8501>.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Server + sim state |
| `GET` | `/api/config/scenarios` | Available scenario definitions |
| `GET` | `/api/config/planners` | Available planner names |
| `POST` | `/api/experiments` | Create a new experiment |
| `GET` | `/api/experiments` | List all experiments |
| `GET` | `/api/experiments/{id}` | Experiment detail with plan runs |
| `GET` | `/api/experiments/{id}/aggregates` | Cross-trial metric averages |
| `POST` | `/api/experiments/{id}/run` | Launch the next trial |
| `POST` | `/api/experiments/{id}/stop` | Gracefully stop the running sim |
| `GET` | `/api/experiments/{id}/status` | Current sim state |
| `GET` | `/api/metrics/{run_id}` | All metrics for a plan run |
| `GET` | `/api/metrics/{run_id}/trajectory` | Robot trajectory (x, y, step) |
| `GET` | `/api/runs/{run_id}` | Plan run detail |
| `WS` | `/ws/telemetry` | Live event stream (WebSocket) |

---

## Mock ROS 2 Topics

The `ros_mock/` package exposes an asyncio-based pub/sub system that mirrors
the `rclpy` API surface. No ROS 2 installation is required.

| Topic | Message type | Publisher | Subscriber |
|-------|-------------|-----------|-----------|
| `/dt/odometry` | `OdometryMsg` | `run_experiment.py` (via SimManager) | `ROSBridgeService` |
| `/dt/plan_status` | `PlanStatusMsg` | `run_experiment.py` | `ROSBridgeService` |
| `/dt/metrics` | `PerformanceMetricsMsg` | `run_experiment.py` | `ROSBridgeService` |

---

## Database Schema

SQLite at runtime, Oracle DDL annotations included on every column for easy
migration.  Set `DATABASE_URL` in `.env` to an `cx_Oracle` or `oracledb` URL
to switch to Oracle.

### EXPERIMENTS

| Column | Type | Notes |
|--------|------|-------|
| EXPERIMENT_ID | INTEGER PK | Oracle: NUMBER(10) |
| EXPERIMENT_NAME | VARCHAR(256) | |
| PLANNER_TYPE | VARCHAR(64) | `waypoint` or `rrt` |
| SCENARIO_NAME | VARCHAR(64) | YAML file key |
| STATUS | VARCHAR(32) | `queued` / `running` / `completed` / `failed` |
| CONFIG_JSON | TEXT | Serialised experiment parameters |
| LOG_DIR | VARCHAR(512) | Path to trajectory files |
| CREATED_AT | DATETIME | |
| FINISHED_AT | DATETIME | Nullable |

### PLAN_RUNS

| Column | Type | Notes |
|--------|------|-------|
| RUN_ID | INTEGER PK | Oracle: NUMBER(10) |
| EXPERIMENT_ID | INTEGER FK | → EXPERIMENTS |
| TRIAL_NUMBER | INTEGER | 1-based |
| STATUS | VARCHAR(32) | `running` / `completed` / `failed` |
| GOAL_REACHED | BOOLEAN | |
| START_TIME | DATETIME | |
| END_TIME | DATETIME | Nullable |

### PERFORMANCE_METRICS

| Column | Type | Notes |
|--------|------|-------|
| METRIC_ID | INTEGER PK | Oracle: NUMBER(10) |
| RUN_ID | INTEGER FK | → PLAN_RUNS |
| METRIC_NAME | VARCHAR(128) | e.g. `path_length` |
| METRIC_VALUE | FLOAT | |
| RECORDED_AT | DATETIME | |

### ROBOT_STATES

| Column | Type | Notes |
|--------|------|-------|
| STATE_ID | INTEGER PK | Oracle: NUMBER(10) |
| RUN_ID | INTEGER FK | → PLAN_RUNS |
| SIM_STEP | INTEGER | |
| POSITION_X | FLOAT | |
| POSITION_Y | FLOAT | |
| ORIENTATION | FLOAT | Yaw in radians |
| LINEAR_VEL | FLOAT | |
| ANGULAR_VEL | FLOAT | |
| RECORDED_AT | DATETIME | |

---

## Offline Validation (no Isaac Sim)

Run a 2-D kinematic simulation of either planner without launching Isaac Sim:

```bash
# Validate all planners on all scenarios, print a comparison table
python sim/scripts/validate_plan.py --planner all --scenario all

# JSON output for programmatic use
python sim/scripts/validate_plan.py --planner rrt --scenario obstacle_course --json
```

---

## Running Tests

```bash
conda activate env_isaaclab
pytest tests/ -v
```

Tests do **not** require Isaac Sim.  The API tests spin up FastAPI with an
in-memory SQLite database.  The planner tests use the pure-Python kinematic
simulator in `sim/scripts/validate_plan.py`.

---

## Project Structure

```
robotics-digital-twin/
├── .env.example                 # Environment variable template
├── requirements.txt             # pip dependencies
├── ros_mock/                    # Mock ROS 2 pub/sub (asyncio)
│   ├── messages.py              # ROS 2-style message dataclasses
│   ├── topic.py                 # TopicRegistry + Topic pub/sub
│   └── node.py                  # Node, Publisher, Subscription, Timer
├── backend/
│   ├── main.py                  # FastAPI app + lifespan
│   ├── config.py                # Pydantic settings from .env
│   ├── schemas.py               # Request / response models
│   ├── db/
│   │   ├── database.py          # Engine, session factory, init_db
│   │   ├── models.py            # ORM models (Oracle-style naming)
│   │   └── crud.py              # Async DB operations
│   ├── services/
│   │   ├── sim_manager.py       # Launch / monitor Isaac Lab subprocess
│   │   └── ros_bridge.py        # Event dispatcher → DB + WebSocket
│   └── routers/
│       ├── experiments.py       # Experiment CRUD endpoints
│       ├── planning.py          # Launch / stop / status endpoints
│       └── metrics.py           # Metrics, trajectory, WebSocket
├── sim/
│   ├── assets/scenarios/        # YAML scenario definitions
│   │   ├── straight_line.yaml
│   │   └── obstacle_course.yaml
│   ├── planners/
│   │   ├── base_planner.py      # Pose2D, Waypoint, Obstacle, BasePlanner
│   │   ├── waypoint_planner.py  # P-controller baseline
│   │   └── rrt_planner.py       # RRT + path smoothing
│   ├── envs/
│   │   ├── go2_nav_env_cfg.py   # Isaac Lab environment config (Go2)
│   │   └── go2_nav_env.py       # Gymnasium-registered env wrapper
│   └── scripts/
│       ├── run_experiment.py    # Isaac Sim subprocess entry point
│       └── validate_plan.py     # Offline 2-D kinematic validation
├── dashboard/
│   ├── app.py                   # Streamlit entry point
│   ├── components/
│   │   ├── api_client.py        # Typed requests wrapper
│   │   └── charts.py            # Plotly chart helpers
│   └── pages/
│       ├── experiments.py       # Create / manage experiments
│       ├── comparison.py        # Cross-planner metric comparison
│       └── live_monitor.py      # Live trajectory + telemetry
├── tests/
│   ├── test_ros_mock.py         # Unit tests for mock ROS 2 layer
│   ├── test_api.py              # FastAPI smoke tests (in-memory DB)
│   └── test_planners.py         # Planner unit + integration tests
└── logs/                        # SQLite DB + experiment trajectory JSON
```

---

## Architecture Decisions

### Why mock ROS 2?

ROS 2 installation on Windows requires WSL2 or Docker and adds significant
setup complexity. The `ros_mock/` package reproduces the rclpy API surface
(`Node`, `Publisher`, `Subscription`, `Timer`) using Python's built-in
`asyncio.Queue`. This allows the architecture diagram on the resume to be
accurate while keeping the project runnable on a plain Windows conda
environment.

### Why Oracle-style schema with SQLite?

Oracle Database is listed on the resume as the production data store. The
schema uses Oracle naming conventions (UPPERCASE table/column names, `NUMBER`
type comments) and the `DATABASE_URL` environment variable can be changed to
a `cx_Oracle` or `python-oracledb` connection string without any model
changes. SQLite via `aiosqlite` keeps local development dependency-free.

### Why subprocess communication?

Isaac Lab scripts run under their own Python interpreter (`isaaclab.bat -p`).
Communicating via `stdout` JSON lines decouples the planner process from the
FastAPI event loop and avoids shared-memory or IPC complexity. The same
pattern is used in the companion `quadruped-drl-platform` project.
