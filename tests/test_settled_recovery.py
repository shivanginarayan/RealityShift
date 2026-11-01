import json
import zipfile

import gymnasium as gym
import numpy as np

from control.settled_recovery import ConfirmedFailureDetector, SettledRecoveryController
from tests.test_recovery import observation


def test_recorded_strategy_comparison_is_verified_without_new_trials():
    from evaluation.verify_settled import verify
    assert verify() == {'verified': True, 'new_developer_episodes_rescored': 30,
                        'reused_baseline_episodes_verified': 30,
                        'model_calls': 0, 'new_simulation_trials': 0}


def test_sustained_stall_requires_confirmation_and_resets():
    detector = ConfirmedFailureDetector()
    for _ in range(30):
        assert detector.update(observation()) is None
    assert detector.update(observation()) == "stall"
    detector.reset()
    assert detector.update(observation()) is None


def test_nominal_recorded_transient_stall_is_not_confirmed():
    detector = ConfirmedFailureDetector()
    with zipfile.ZipFile('docs/evidence/recovery-v2/trajectories.zip') as bundle:
        rows = [json.loads(line) for line in bundle.read(
            'final/original_v1/nominal/seed1/trajectory.jsonl').splitlines()]
    for row in rows:
        if row['phase'] != 'push':
            detector.reset()
        else:
            assert detector.update(row['observation_before']) is None


def test_confirmation_does_not_delay_contact_loss_or_overshoot():
    detector = ConfirmedFailureDetector()
    detector.update(observation())
    far = observation(tip=[-.3, 0., -.16])
    for _ in range(7):
        assert detector.update(far) is None
    assert detector.update(far) == 'lost_contact'
    detector.reset()
    detector.update(observation())
    detector.update(observation(.27))
    assert detector.update(observation(.36)) == 'overshoot'


def test_settled_policy_still_exhausts_bounded_retries_on_unreachable_targets():
    env = gym.make('Pusher-v5')
    try:
        controller = SettledRecoveryController(env.unwrapped.model)
        obs = observation(tip=[-.6, .6, 0.])
        for _ in range(600):
            controller.target(obs)
        assert controller.phase == 'exhausted'
        assert controller.retries == 2
        assert controller.target(obs)[0] is None
    finally:
        env.close()


def test_dynamics_strategy_is_deterministic_and_leaves_live_state_untouched():
    env = gym.make('Pusher-v5')
    try:
        obs, _ = env.reset(seed=0)
        before_qpos = env.unwrapped.data.qpos.copy()
        before_qvel = env.unwrapped.data.qvel.copy()
        first = SettledRecoveryController(env.unwrapped.model)
        second = SettledRecoveryController(env.unwrapped.model)
        for _ in range(4):
            action = first.action(obs)
            np.testing.assert_array_equal(action, second.action(obs))
            assert np.isfinite(action).all() and np.max(np.abs(action)) <= 2
        np.testing.assert_array_equal(env.unwrapped.data.qpos, before_qpos)
        np.testing.assert_array_equal(env.unwrapped.data.qvel, before_qvel)
    finally:
        env.close()
