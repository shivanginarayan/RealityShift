"""Increment 2 strategies, preserving the measured increment 1 controller."""
import mujoco
import numpy as np

from control.recovery import FailureDetector, RecoveryConfig, RecoveryController, checked_observation


class ConfirmedFailureDetector(FailureDetector):
    """Require sustained stall evidence, rather than reacting to one window."""

    def reset(self):
        super().reset()
        self.stall_streak = 0

    def update(self, observation):
        reason = super().update(observation)
        self.stall_streak = self.stall_streak + 1 if reason == "stall" else 0
        if reason == "stall" and self.stall_streak < self.config.contact_patience:
            return None
        return reason


class ConfirmedRecoveryController(RecoveryController):
    """Ablation: only change stall confirmation, retain increment 1 tracking."""

    def __init__(self, model, skill=None, config=None):
        super().__init__(model, skill, config)
        self.detector = ConfirmedFailureDetector(self.config, self.skill.stop_distance)

    def diagnostics(self):
        result = super().diagnostics()
        result["policy"] = "developer_confirmed_recovery_v2"
        return result


class SettledRecoveryController(ConfirmedRecoveryController):
    """Nominal inverse-dynamics tracking with bounded velocity/acceleration.

    Fixed developer strategy, not a search over YAML gains. The nominal model
    receives observed robot joints only. Contact forces/shifted physics and
    applied torques are never read. No delay estimation or oracle is used.
    """

    def __init__(self, model, skill=None):
        super().__init__(model, skill, RecoveryConfig(approach_timeout=100,
                         phase_timeout=65, recovery_timeout=180))
        self.dynamics = mujoco.MjData(model)
        self.mass_matrix = np.zeros((model.nv, model.nv))
        # Fixed public strategy bounds, chosen before the comparison.
        self.max_joint_speed = .8
        self.max_joint_acceleration = 2.
        self.response_seconds = .4

    def action(self, observation):
        obs = checked_observation(observation)
        # Reuse the unchanged nominal IK target solver and recovery transitions.
        # Its direct PD torque is intentionally replaced by the dynamics law.
        super().action(obs)
        desired_velocity = np.clip(2 * (self.reference - obs[:7]),
                                   -self.max_joint_speed, self.max_joint_speed)
        if self.phase == "exhausted":
            desired_velocity[:] = 0
        acceleration = np.clip((desired_velocity - obs[7:14]) / self.response_seconds,
                               -self.max_joint_acceleration, self.max_joint_acceleration)
        data = self.dynamics
        data.qpos[:7] = obs[:7]
        data.qvel[:] = 0
        data.qvel[:7] = obs[7:14]
        mujoco.mj_forward(self.model, data)
        mujoco.mj_fullM(self.model, data, self.mass_matrix)
        # Passive joint damping is already exerted by the simulator; compensate
        # its nominal contribution rather than asking a high-gain torque loop
        # to overcome it. Do not use constraint/contact forces from the model.
        torque = (self.mass_matrix[:7, :7] @ acceleration
                  + data.qfrc_bias[:7] - data.qfrc_passive[:7])
        self.previous_action = np.clip(torque, -self.skill.max_torque, self.skill.max_torque)
        return self.previous_action.copy()

    def diagnostics(self):
        result = super().diagnostics()
        result["policy"] = "developer_settled_recovery_v2"
        result["tracking_strategy"] = {"max_joint_speed": self.max_joint_speed,
            "max_joint_acceleration": self.max_joint_acceleration,
            "response_seconds": self.response_seconds}
        return result
