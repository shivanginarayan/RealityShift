"""FIFO command delay with zero commands during warm-up."""
from collections import deque

import numpy as np


class ActionDelay:
    def __init__(self, steps, shape):
        if isinstance(steps, bool) or not isinstance(steps, int) or not 0 <= steps <= 100:
            raise ValueError("delay steps must be an integer in [0, 100]")
        self.steps = steps
        self.shape = shape
        self.reset()

    def reset(self):
        self.queue = deque(np.zeros(self.shape) for _ in range(self.steps))

    def apply(self, action):
        action = np.asarray(action, dtype=float)
        if action.shape != self.shape or not np.isfinite(action).all():
            raise ValueError("action must have the expected shape and finite values")
        self.queue.append(action.copy())
        return self.queue.popleft()
