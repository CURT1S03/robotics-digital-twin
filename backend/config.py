"""Application configuration via environment variables / .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Isaac Lab / Sim paths ──────────────────────────────────────────────── #
    isaacsim_path: str = r"A:\Projects\IsaacSim\isaac-sim-standalone-5.1.0-windows-x86_64"
    isaaclab_path: str = r"A:\Projects\IsaacLab"
    conda_env_name: str = "env_isaaclab"

    # ── Project root (auto-detected) ─────────────────────────────────────── #
    project_root: Path = Path(__file__).resolve().parent.parent

    # ── Database ─────────────────────────────────────────────────────────── #
    # Set DATABASE_URL in .env to use Oracle:
    #   oracle+cx_oracle://user:pass@host:1521/?service_name=XEPDB1
    database_url: str = ""

    # ── Server ───────────────────────────────────────────────────────────── #
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # ── Simulation defaults ───────────────────────────────────────────────── #
    default_max_steps: int = 2000
    default_num_trials: int = 3
    state_sample_interval: int = 10   # record robot state every N sim steps
    log_dir: Path = Path("logs/experiments")

    # ── Mock ROS 2 ────────────────────────────────────────────────────────── #
    ros_topic_prefix: str = "/dt"

    def model_post_init(self, __context):  # noqa: ANN001
        if not self.database_url:
            db_path = self.project_root / "logs" / "digital_twin.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.database_url = f"sqlite+aiosqlite:///{db_path}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
