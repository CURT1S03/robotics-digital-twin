"""Go2 navigation environment configuration for Isaac Lab.

Defines a flat-terrain, single-robot environment suitable for validating
navigation planning algorithms.  The robot receives velocity commands
(vx, vy, omega) and the environment tracks goal-reaching performance.

Registered tasks:
    Go2-Nav-v0        — training / multi-env validation (1024 envs)
    Go2-Nav-Play-v0   — single-env deterministic evaluation (10 envs)
"""

from __future__ import annotations

import math

import isaaclab.sim as sim_utils
from isaaclab.assets import ArticulationCfg, AssetBaseCfg
from isaaclab.envs import ManagerBasedRLEnvCfg
from isaaclab.managers import (
    EventTermCfg as EventTerm,
    ObservationGroupCfg as ObsGroup,
    ObservationTermCfg as ObsTerm,
    RewardTermCfg as RewTerm,
    SceneEntityCfg,
    TerminationTermCfg as DoneTerm,
)
from isaaclab.scene import InteractiveSceneCfg
from isaaclab.sensors import ContactSensorCfg
from isaaclab.terrains import TerrainImporterCfg
from isaaclab.utils import configclass
from isaaclab.utils.assets import ISAACLAB_NUCLEUS_DIR
from isaaclab.utils.noise import AdditiveUniformNoiseCfg as Unoise
from isaaclab.envs import mdp

from isaaclab_assets.robots.unitree import UNITREE_GO2_CFG


##
# Scene
##


@configclass
class Go2NavSceneCfg(InteractiveSceneCfg):
    """Flat-terrain scene for Go2 navigation experiments."""

    # ── Terrain ────────────────────────────────────────────────────────── #
    terrain = TerrainImporterCfg(
        prim_path="/World/ground",
        terrain_type="plane",
        collision_group=-1,
        physics_material=sim_utils.RigidBodyMaterialCfg(
            friction_combine_mode="multiply",
            restitution_combine_mode="multiply",
            static_friction=1.0,
            dynamic_friction=1.0,
        ),
        debug_vis=False,
    )

    # ── Robot ──────────────────────────────────────────────────────────── #
    robot: ArticulationCfg = UNITREE_GO2_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")

    # ── Contact Sensors ────────────────────────────────────────────────── #
    contact_forces = ContactSensorCfg(
        prim_path="{ENV_REGEX_NS}/Robot/.*",
        history_length=3,
        track_air_time=True,
    )

    # ── Lighting ───────────────────────────────────────────────────────── #
    sky_light = AssetBaseCfg(
        prim_path="/World/Light",
        spawn=sim_utils.DomeLightCfg(intensity=750.0, color=(0.9, 0.9, 0.9)),
    )


##
# MDP components
##


@configclass
class Go2NavObservationsCfg:
    """Observations seen by both the planner and the policy."""

    @configclass
    class PolicyCfg(ObsGroup):
        """Minimal proprioceptive observations for velocity tracking."""

        # Base kinematics (in robot frame)
        base_lin_vel = ObsTerm(func=mdp.base_lin_vel, noise=Unoise(n_min=-0.1, n_max=0.1))
        base_ang_vel = ObsTerm(func=mdp.base_ang_vel, noise=Unoise(n_min=-0.2, n_max=0.2))
        projected_gravity = ObsTerm(
            func=mdp.projected_gravity, noise=Unoise(n_min=-0.05, n_max=0.05)
        )
        # Velocity command fed in from the planner (vx, vy, omega)
        velocity_commands = ObsTerm(func=mdp.generated_commands, params={"command_name": "base_velocity"})
        # Joint state
        joint_pos = ObsTerm(func=mdp.joint_pos_rel, noise=Unoise(n_min=-0.01, n_max=0.01))
        joint_vel = ObsTerm(func=mdp.joint_vel_rel, noise=Unoise(n_min=-1.5, n_max=1.5))

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True

    policy: PolicyCfg = PolicyCfg()


@configclass
class Go2NavActionsCfg:
    """Joint position actions for locomotion."""

    joint_pos = mdp.JointPositionActionCfg(
        asset_name="robot",
        joint_names=[".*"],
        scale=0.25,
        use_default_offset=True,
    )


@configclass
class Go2NavCommandsCfg:
    """Velocity commands injected by the planner."""

    base_velocity = mdp.UniformVelocityCommandCfg(
        asset_name="robot",
        resampling_time_range=(10.0, 10.0),  # hold command for full episode
        debug_vis=False,
        ranges=mdp.UniformVelocityCommandCfg.Ranges(
            lin_vel_x=(-1.0, 1.0),
            lin_vel_y=(-0.5, 0.5),
            ang_vel_z=(-1.0, 1.0),
            heading=(-math.pi, math.pi),
        ),
    )


@configclass
class Go2NavEventsCfg:
    """Randomisation events for domain randomisation."""

    physics_material = EventTerm(
        func=mdp.randomize_rigid_body_material,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=".*"),
            "static_friction_range": (0.8, 1.2),
            "dynamic_friction_range": (0.6, 1.0),
            "restitution_range": (0.0, 0.0),
            "num_buckets": 64,
        },
    )

    reset_base = EventTerm(
        func=mdp.reset_root_state_uniform,
        mode="reset",
        params={
            "pose_range": {"x": (-0.5, 0.5), "y": (-0.5, 0.5), "yaw": (-3.14, 3.14)},
            "velocity_range": {
                "x": (-0.5, 0.5),
                "y": (-0.5, 0.5),
                "z": (-0.5, 0.5),
                "roll": (-0.5, 0.5),
                "pitch": (-0.5, 0.5),
                "yaw": (-0.5, 0.5),
            },
        },
    )

    reset_robot_joints = EventTerm(
        func=mdp.reset_joints_by_scale,
        mode="reset",
        params={"position_range": (0.5, 1.5), "velocity_range": (0.0, 0.0)},
    )


@configclass
class Go2NavRewardsCfg:
    """Rewards for velocity-command tracking and locomotion quality."""

    # Primary: track planner velocity commands
    track_lin_vel_xy_exp = RewTerm(
        func=mdp.track_lin_vel_xy_exp,
        weight=1.5,
        params={"command_name": "base_velocity", "std": math.sqrt(0.25)},
    )
    track_ang_vel_z_exp = RewTerm(
        func=mdp.track_ang_vel_z_exp,
        weight=0.75,
        params={"command_name": "base_velocity", "std": math.sqrt(0.25)},
    )
    # Penalties
    dof_torques_l2 = RewTerm(func=mdp.joint_torques_l2, weight=-2.0e-4)
    dof_acc_l2 = RewTerm(func=mdp.joint_acc_l2, weight=-2.5e-7)
    action_rate_l2 = RewTerm(func=mdp.action_rate_l2, weight=-0.01)
    flat_orientation_l2 = RewTerm(func=mdp.flat_orientation_l2, weight=-5.0)
    base_height_l2 = RewTerm(
        func=mdp.base_height_l2,
        weight=-10.0,
        params={"asset_cfg": SceneEntityCfg("robot"), "target_height": 0.34},
    )


@configclass
class Go2NavTerminationsCfg:
    """Episode termination conditions."""

    time_out = DoneTerm(func=mdp.time_out, time_out=True)
    base_contact = DoneTerm(
        func=mdp.illegal_contact,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names="base"), "threshold": 1.0},
    )


##
# Environment configuration
##


@configclass
class Go2NavEnvCfg(ManagerBasedRLEnvCfg):
    """Full environment config for Go2 navigation validation."""

    scene: Go2NavSceneCfg = Go2NavSceneCfg(num_envs=1024, env_spacing=2.5)
    observations: Go2NavObservationsCfg = Go2NavObservationsCfg()
    actions: Go2NavActionsCfg = Go2NavActionsCfg()
    commands: Go2NavCommandsCfg = Go2NavCommandsCfg()
    events: Go2NavEventsCfg = Go2NavEventsCfg()
    rewards: Go2NavRewardsCfg = Go2NavRewardsCfg()
    terminations: Go2NavTerminationsCfg = Go2NavTerminationsCfg()

    def __post_init__(self):
        super().__post_init__()
        self.decimation = 4
        self.episode_length_s = 20.0
        self.sim.dt = 0.005
        self.sim.render_interval = self.decimation
        self.sim.physics_material = sim_utils.RigidBodyMaterialCfg(
            friction_combine_mode="multiply",
            restitution_combine_mode="multiply",
            static_friction=1.0,
            dynamic_friction=1.0,
        )
        self.sim.physx.bounce_threshold_velocity = 0.2
        self.sim.physx.bounce_threshold_velocity = 0.01
        self.sim.physx.gpu_collision_stack_size = 2**24


@configclass
class Go2NavEnvCfg_PLAY(Go2NavEnvCfg):
    """Single-env deterministic config for evaluation/deploy."""

    def __post_init__(self):
        super().__post_init__()
        self.scene.num_envs = 10
        self.scene.env_spacing = 3.0
        # Disable randomisation
        self.events.physics_material = None  # type: ignore[assignment]
        self.events.reset_base = EventTerm(
            func=mdp.reset_root_state_uniform,
            mode="reset",
            params={
                "pose_range": {},
                "velocity_range": {},
            },
        )
        self.observations.policy.enable_corruption = False
