"""Isaac Lab simulation manager — wraps run_experiment.py as a subprocess.

Lifecycle:
    IDLE → start_experiment() → RUNNING → (subprocess exits) → IDLE
    Any state → stop() → STOPPING → IDLE

The subprocess prints structured JSON lines to stdout:
    {"type": "odometry",  "run_id": 1, "x": 0.5, "y": 1.2, ...}
    {"type": "plan_status", "run_id": 1, "status": "executing", ...}
    {"type": "metrics",   "run_id": 1, "path_length": 5.3, ...}
    {"type": "done",      "run_id": 1, "goal_reached": true}

The manager dispatches these to an optional *on_output* callback (used by
the ROS bridge service to persist data and fan out to WebSocket clients).
"""

from __future__ import annotations

import asyncio
import enum
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from backend.config import settings

logger = logging.getLogger(__name__)


class SimState(str, enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"


class SimManager:
    """Manages the Isaac Lab experiment subprocess."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._state: SimState = SimState.IDLE
        self._current_experiment_id: int | None = None
        self._current_run_id: int | None = None
        self._log_dir: str | None = None
        self._on_output: Callable[[dict], None] | None = None
        self._reader_task: asyncio.Task | None = None
        self._last_error: str | None = None

    # ── Properties ─────────────────────────────────────────────────────── #

    @property
    def state(self) -> SimState:
        return self._state

    @property
    def current_experiment_id(self) -> int | None:
        return self._current_experiment_id

    @property
    def current_run_id(self) -> int | None:
        return self._current_run_id

    @property
    def log_dir(self) -> str | None:
        return self._log_dir

    @property
    def last_error(self) -> str | None:
        return self._last_error

    # ── Launch ─────────────────────────────────────────────────────────── #

    def start_experiment(
        self,
        experiment_id: int,
        run_id: int,
        planner_type: str,
        scenario_name: str,
        trial_number: int = 1,
        max_steps: int | None = None,
        headless: bool = True,
        planner_params: dict | None = None,
        on_output: Callable[[dict], None] | None = None,
    ) -> str:
        """Launch run_experiment.py as a subprocess.

        Returns the resolved log directory path.
        """
        if self._state != SimState.IDLE:
            raise RuntimeError(f"Cannot start experiment while in state: {self._state.value}")

        isaaclab_cmd = self._resolve_isaaclab_python()
        script = str(settings.project_root / "sim" / "scripts" / "run_experiment.py")

        cmd = [
            *isaaclab_cmd,
            script,
            "--experiment_id", str(experiment_id),
            "--run_id", str(run_id),
            "--planner", planner_type,
            "--scenario", scenario_name,
            "--trial_number", str(trial_number),
        ]
        if headless:
            cmd.append("--headless")
        if max_steps is not None:
            cmd.extend(["--max_steps", str(max_steps)])
        if planner_params:
            cmd.extend(["--planner_params", json.dumps(planner_params)])

        resolved_log = str(
            settings.log_dir
            / f"exp_{experiment_id}"
            / f"run_{run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        cmd.extend(["--log_dir", resolved_log])

        logger.info("Launching: %s", " ".join(cmd))

        proc_env = {**os.environ, "PYTHONUNBUFFERED": "1"}

        if sys.platform == "win32":
            cflags = subprocess.CREATE_NEW_PROCESS_GROUP if headless else subprocess.CREATE_NEW_CONSOLE
        else:
            cflags = 0

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(settings.project_root),
            env=proc_env,
            creationflags=cflags,
        )
        logger.info("Subprocess PID: %d", self._process.pid)

        self._state = SimState.RUNNING
        self._current_experiment_id = experiment_id
        self._current_run_id = run_id
        self._log_dir = resolved_log
        self._on_output = on_output
        self._last_error = None

        self._reader_task = asyncio.ensure_future(self._read_output())
        return resolved_log

    # ── Stop ───────────────────────────────────────────────────────────── #

    async def stop(self, timeout: float = 15.0) -> None:
        """Gracefully terminate the subprocess."""
        if self._process is None or self._state == SimState.IDLE:
            return

        self._state = SimState.STOPPING
        logger.info("Stopping subprocess PID %d…", self._process.pid)

        if sys.platform == "win32":
            self._process.send_signal(subprocess.signal.CTRL_BREAK_EVENT)
        else:
            self._process.terminate()

        try:
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self._process.wait),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Subprocess did not exit in %.0fs — killing.", timeout)
            self._process.kill()

        self._reset()

    # ── Internal ───────────────────────────────────────────────────────── #

    async def _read_output(self) -> None:
        """Stream subprocess stdout and dispatch JSON events."""
        assert self._process and self._process.stdout

        loop = asyncio.get_event_loop()
        try:
            while True:
                line = await loop.run_in_executor(None, self._process.stdout.readline)
                if not line:
                    break
                line = line.rstrip()
                logger.debug("[sim] %s", line)
                try:
                    event = json.loads(line)
                    if self._on_output:
                        self._on_output(event)
                except json.JSONDecodeError:
                    pass  # not every line is JSON (Isaac Lab startup messages)
        except Exception:
            logger.exception("Error reading subprocess output")
        finally:
            exit_code = await loop.run_in_executor(None, self._process.wait)
            logger.info("Subprocess exited with code %d", exit_code)
            if exit_code != 0:
                self._last_error = f"Process exited with code {exit_code}"
            self._reset()

    def _reset(self) -> None:
        self._process = None
        self._state = SimState.IDLE
        self._current_experiment_id = None
        self._current_run_id = None

    def _resolve_isaaclab_python(self) -> list[str]:
        """Return the command prefix to invoke Isaac Lab's Python.

        Priority:
        1. Conda env python (pip-installed Isaac Lab)
        2. Isaac Lab _isaac_sim/python.bat (standalone symlink)
        3. Isaac Sim standalone python.bat
        """
        # 1. Conda env python
        conda_python = Path(os.environ.get("CONDA_PREFIX", "")) / "python.exe"
        if not conda_python.exists():
            # Try resolving from settings.conda_env_name
            from pathlib import PureWindowsPath
            miniconda = Path(os.environ.get("USERPROFILE", "")) / "Miniconda3"
            conda_python = miniconda / "envs" / settings.conda_env_name / "python.exe"
        if conda_python.exists():
            logger.info("Using conda Python: %s", conda_python)
            return [str(conda_python)]

        # 2. Isaac Lab bundled python.bat
        if sys.platform == "win32":
            isaac_python = Path(settings.isaaclab_path) / "_isaac_sim" / "python.bat"
            if isaac_python.exists():
                return ["cmd", "/c", str(isaac_python)]
            # 3. Fallback: Isaac Sim's python.bat
            return ["cmd", "/c", str(Path(settings.isaacsim_path) / "python.bat")]
        else:
            isaac_python = Path(settings.isaaclab_path) / "_isaac_sim" / "python.sh"
            if isaac_python.exists():
                return [str(isaac_python)]
            return [str(Path(settings.isaacsim_path) / "python.sh")]
