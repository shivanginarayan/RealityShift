"""Nominal model-based reference controller; no physics-shift adaptation."""
import mujoco
import numpy as np
from scipy.optimize import least_squares


class PushingController:
    def __init__(self, model):
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
        behind[:2] -= .09 * direction
        if self.phase == 'approach':
            target = behind.copy()
            target[2] = -.16
            if np.linalg.norm(tip - target) < .04:
                self.phase = 'lower'
        elif self.phase == 'lower':
            target = behind.copy()
            if np.linalg.norm(tip - target) < .05:
                self.phase = 'push'
        else:
            target = obj.copy()
            target[:2] -= .025 * direction
            if distance < .05:
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
        return np.clip(60 * (self.reference - observation[:7]) - 4 * observation[7:14], -2, 2)






