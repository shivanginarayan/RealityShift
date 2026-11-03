"""V3 command-history delay, including a scheduled onset. Never a policy input."""
from collections import deque

import gymnasium as gym
import numpy as np


class DelayedPusher(gym.Wrapper):
    def __init__(self, delay_steps=4, onset_step=0, horizon=300):
        if type(delay_steps) is not int or not 0 <= delay_steps <= 8:
            raise ValueError('delay_steps must be an integer in [0, 8]')
        if type(onset_step) is not int or not 0 <= onset_step < horizon:
            raise ValueError('onset_step must be within the episode')
        super().__init__(gym.make('Pusher-v5', max_episode_steps=horizon))
        self.delay_steps, self.onset_step = delay_steps, onset_step
        self.command_index = 0
        self.history = deque(maxlen=delay_steps)
        self.last_applied_action = np.zeros(7)

    def reset(self, **kwargs):
        self.command_index = 0
        self.history.clear()
        self.history.extend(np.zeros(7) for _ in range(self.delay_steps))
        self.last_applied_action = np.zeros(7)
        return self.env.reset(**kwargs)

    def step(self, action):
        action = np.asarray(action, dtype=float)
        if action.shape != (7,) or not np.isfinite(action).all() or np.max(np.abs(action)) > 2:
            raise ValueError('Expected seven finite torques within [-2, 2]')
        delayed = self.history[0].copy() if self.delay_steps else action.copy()
        self.last_applied_action = delayed if self.command_index >= self.onset_step else action.copy()
        self.history.append(action.copy())
        self.command_index += 1
        return self.env.step(self.last_applied_action)
