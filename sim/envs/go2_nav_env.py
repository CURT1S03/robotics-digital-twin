"""Gymnasium task registration for Go2 navigation environments."""

import gymnasium as gym

gym.register(
    id="Go2-Nav-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": "sim.envs.go2_nav_env_cfg:Go2NavEnvCfg",
    },
)

gym.register(
    id="Go2-Nav-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": "sim.envs.go2_nav_env_cfg:Go2NavEnvCfg_PLAY",
    },
)
