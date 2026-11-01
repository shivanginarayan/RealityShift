"""Nominal model-based reference controller; no physics-shift adaptation."""
import mujoco
import numpy as np
from scipy.optimize import least_squares
from pathlib import Path
from control.skill_schema import load_skill


class PushingController:
    def __init__(self, model, skill=None):
        self.skill = skill or load_skill(Path(__file__).parents[1] / 'skills/initial.yaml')
        self.previous_action = np.zeros(7)
        self.model = model
        self.kinematics = mujoco.MjData(model)
        self.tip_id = model.body('tips_arm').id
        self.reference = np.array([0., .6, 0., -1., 0., -.4, 0.])
        self.phase = 'approach'

    def action(self, observation):
        tip, obj, goal = observation[14:17], observation[17:20], observation[20:23]
        direction = goal[:2] - obj[:2]
        distance = np.linalg.norm(direction)
        direction /= max(distance, 1e-9)
        behind = obj.copy()
        behind[:2] -= self.skill.approach_offset * direction
        if self.phase == 'approach':
            target = behind.copy()
            target[2] = self.skill.approach_height
            if np.linalg.norm(tip - target) < .04:
                self.phase = 'lower'
        elif self.phase == 'lower':
            target = behind.copy()
            if np.linalg.norm(tip - target) < .05:
                self.phase = 'push'
        else:
            target = obj.copy()
            target[:2] -= self.skill.push_offset * direction
            if distance < self.skill.stop_distance:
                target = tip.copy()
        def residual(q):
            self.kinematics.qpos[:7] = q
            mujoco.mj_kinematics(self.model, self.kinematics)
            return np.concatenate((10 * (self.kinematics.xpos[self.tip_id] - target),
                                   np.array([.5 * np.dot(self.kinematics.xmat[self.tip_id].reshape(3, 3)[:, 1], np.r_[direction, 0.])]),
                                   np.array([.5 * self.kinematics.xmat[self.tip_id].reshape(3, 3)[2, 1]]),
                                   .005 * (q - self.reference)))
        solution = least_squares(residual, self.reference,
                                 bounds=(self.model.jnt_range[:7, 0] + .001,
                                         self.model.jnt_range[:7, 1] - .001),
                                 max_nfev=60)
        self.reference = solution.x
        raw = np.clip(self.skill.proportional_gain * (self.reference - observation[:7])
                      - self.skill.damping_gain * observation[7:14],
                      -self.skill.max_torque, self.skill.max_torque)
        alpha = self.skill.action_smoothing
        self.previous_action = alpha * raw + (1 - alpha) * self.previous_action
        return self.previous_action.copy()






