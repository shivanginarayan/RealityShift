"""Developer increment after frozen v2: tracking memory and observed braking.

Never used by the frozen v2 bridge. No shifted dynamics, contact forces,
intervention labels or evaluation metadata enter this controller.
"""
from collections import deque

import mujoco
import numpy as np

from control.reachable_recovery import ReachableStrategyController
from control.recovery import checked_observation


class ProgressRecoveryController(ReachableStrategyController):
    def __init__(self, model, strategy=None, *, tracking_memory=True, braking=True):
        super().__init__(model, strategy)
        self.tracking_memory = tracking_memory
        self.braking = braking
        self.tracking_debt = 0.
        self.object_history = deque(maxlen=5)
        self.push_history = deque(maxlen=self.config.window)
        self.braking_active = False
        self.braking_started = 0
        self.braking_target = None
        self.braking_joints = None

    def _begin(self, reason, obs, force_plan=None):
        self.tracking_debt = 0.
        self.braking_active = False
        self.braking_target = None
        self.braking_joints = None
        self.push_history.clear()
        super()._begin(reason, obs, force_plan)

    def target(self, observation):
        obs = checked_observation(observation)
        previous_stage = self.command_stage
        target, direction = super().target(obs)
        obj, goal = obs[17:19], obs[20:22]
        if self.object_history and np.linalg.norm(obj - self.object_history[-1]) > .08:
            self.object_history.clear()
            self.tracking_debt = 0.
            self.braking_active = False
            self.braking_target = None
            self.braking_joints = None
            self.push_history.clear()
        self.object_history.append(obj.copy())
        error = float(np.linalg.norm(goal - obj))
        if self.braking and self.command_stage in ('push', 'correct_push', 'hold'):
            velocity = ((obj - self.object_history[0]) / (.05 * (len(self.object_history) - 1))
                        if len(self.object_history) > 1 else np.zeros(2))
            closing = float(np.dot(velocity, direction))
            remaining = error - self.skill.stop_distance
            # A short observable stopping corridor, not an estimate of hidden
            # actuator delay or mass. Release after twelve unsuccessful samples.
            imminent = error < .10 and closing > .03 and remaining < .2 * closing
            if not self.braking_active and imminent:
                self.braking_active = True
                self.braking_started = self.step
                self.braking_target = obs[14:17].copy()
                self.braking_joints = obs[:7].copy()
                self._event('observed_closing_brake', self.phase)
            if self.command_stage == 'hold':
                if not self.braking_active:
                    self.braking_started = self.step
                    self.braking_target = obs[14:17].copy()
                    self.braking_joints = obs[:7].copy()
                self.braking_active = True
            if self.braking_active:
                if self.command_stage != 'hold' and self.step - self.braking_started >= 12:
                    self.braking_active = False
                    self.braking_target = None
                    self.braking_joints = None
                    self.object_history.clear()
                else:
                    if self.braking_target is None:
                        self.braking_target = obs[14:17].copy()
                    target = self.braking_target.copy()
                    self.tracking_debt = 0.
                    self._record_target(target, self.command_stage)
        active_push = self.command_stage in ('push', 'correct_push', 'repush')
        if not active_push or previous_stage != self.command_stage:
            self.tracking_debt = 0.
            self.push_history.clear()
        if active_push:
            self.push_history.append((obj.copy(), error))
        productive = (len(self.push_history) == self.config.window
                      and self.push_history[0][1] - error >= self.config.min_progress)
        if (self.tracking_memory and active_push and self.stable and not self.braking_active
                and productive and target is not None and np.linalg.norm(obs[14:17] - obs[17:20]) < .10):
            lag = float(np.dot(target[:2] - obs[14:16], direction))
            # Integrate only observed forward tracking error. Both accumulated
            # travel and each update are bounded independently of episode length.
            self.tracking_debt = float(np.clip(self.tracking_debt + np.clip(.05 * lag, -.002, .002), 0., .03))
            if self.tracking_debt > 0:
                target = target.copy()
                target[:2] += self.tracking_debt * direction
                self._record_target(target, self.command_stage)
        return target, direction

    def action(self, observation):
        obs = checked_observation(observation)
        action = super().action(obs)
        if self.braking and self.braking_active and self.command_stage in ('push', 'correct_push', 'hold'):
            return self._brake_action(obs)
        return action

    def _brake_action(self, obs):
        # Hold the observed joint pose as well as damping velocity. Pure
        # velocity damping lets contact loads slowly displace the arm and
        # escape the goal. Reuse the existing nominal tracking bounds.
        velocity = np.clip(2 * (self.braking_joints - obs[:7]), -.8, .8)
        acceleration = np.clip((velocity - obs[7:14]) / .4, -2., 2.)
        self.dynamics.qpos[:7] = obs[:7]
        self.dynamics.qvel[:] = 0.
        self.dynamics.qvel[:7] = obs[7:14]
        mujoco.mj_forward(self.model, self.dynamics)
        mujoco.mj_fullM(self.model, self.dynamics, self.mass_matrix)
        torque = self.mass_matrix[:7, :7] @ acceleration + self.dynamics.qfrc_bias[:7] - self.dynamics.qfrc_passive[:7]
        self.previous_action = np.clip(torque, -self.skill.max_torque, self.skill.max_torque)
        return self.previous_action.copy()

    def diagnostics(self):
        result = super().diagnostics()
        result.update(policy='developer_progress_recovery', tracking_debt_m=self.tracking_debt,
                      braking_active=self.braking_active)
        return result
