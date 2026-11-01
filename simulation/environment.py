"""Shift wrapper; physics settings remain in developer/evaluator metadata."""
import gymnasium as gym
import mujoco
import numpy as np

from simulation.delay import ActionDelay
from simulation.scenarios import SCENARIOS


class ShiftedPusher(gym.Wrapper):
    def __init__(self, scenario_id="nominal", horizon=300):
        if scenario_id not in SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario_id}")
        super().__init__(gym.make("Pusher-v5", max_episode_steps=horizon))
        self.scenario = SCENARIOS[scenario_id]
        model = self.unwrapped.model
        body = model.body("object").id
        self.nominal_mass = float(model.body_mass[body])
        model.body_mass[body] *= self.scenario.mass_scale
        model.body_inertia[body] *= self.scenario.mass_scale
        mujoco.mj_setConst(model, self.unwrapped.data)
        self.actual_mass = float(model.body_mass[body])
        self.delay = ActionDelay(self.scenario.delay_steps, self.action_space.shape)
        self.last_applied_action = np.zeros(self.action_space.shape)

    def reset(self, **kwargs):
        self.delay.reset()
        self.last_applied_action = np.zeros(self.action_space.shape)
        return self.env.reset(**kwargs)

    def step(self, action):
        action = np.asarray(action, dtype=float)
        if action.shape != self.action_space.shape or not np.isfinite(action).all():
            raise ValueError("Invalid action shape or non-finite values")
        if np.any(action < self.action_space.low) or np.any(action > self.action_space.high):
            raise ValueError("Action exceeds actuator bounds")
        self.last_applied_action = self.delay.apply(action)
        return self.env.step(self.last_applied_action)

    def developer_manifest(self):
        return {**self.scenario.manifest(), "nominal_object_mass_kg": self.nominal_mass,
                "actual_object_mass_kg": self.actual_mass,
                "delay_seconds": self.scenario.delay_steps * self.unwrapped.dt}
