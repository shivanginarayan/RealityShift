import gymnasium as gym
import numpy as np

from control.controller import PushingController
from simulation.nominal import run_episode


def test_nominal_seed42_reaches_and_settles(tmp_path):
    result = run_episode(42, tmp_path)
    assert result["success"]
    assert result["steps"] == 300
    assert result["max_abs_action"] <= 2


def test_controller_does_not_modify_live_simulator_state():
    env = gym.make("Pusher-v5")
    try:
        observation, _ = env.reset(seed=0)
        before = env.unwrapped.data.qpos.copy()
        action = PushingController(env.unwrapped.model).action(observation)
        np.testing.assert_array_equal(before, env.unwrapped.data.qpos)
        assert np.isfinite(action).all()
        assert np.max(np.abs(action)) <= 2
    finally:
        env.close()
