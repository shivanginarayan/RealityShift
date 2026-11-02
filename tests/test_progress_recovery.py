import json
import zipfile

import gymnasium as gym
import numpy as np
import pytest

from control.progress_recovery import ProgressRecoveryController
from control.reachable_recovery import ReachableStrategyController
from evaluation.benchmark import ROOT
from tests.test_recovery import observation


@pytest.fixture
def controller():
    env = gym.make('Pusher-v5')
    try:
        yield ProgressRecoveryController(env.unwrapped.model)
    finally:
        env.close()


@pytest.fixture
def contact_target(monkeypatch):
    def target(self, obs):
        self.step += 1
        self.command_stage = self.phase
        direction = obs[20:22] - obs[17:19]
        direction /= max(np.linalg.norm(direction), 1e-9)
        point = obs[17:20].copy()
        point[:2] -= .025 * direction
        return self._record_target(point, self.phase), direction
    monkeypatch.setattr(ReachableStrategyController, 'target', target)


def test_tracking_memory_is_bounded_and_requires_observed_contact_tracking(controller, contact_target):
    controller.phase, controller.stable, controller.braking = 'push', True, False
    for i in range(200):
        obs = observation(x=i * .001, tip=[i * .001 - .05, 0., -.275], goal=.5)
        target, _ = controller.target(obs)
    assert controller.tracking_debt == pytest.approx(.03)
    assert target[0] == pytest.approx(obs[17] + .005)
    controller.phase = 'hold'
    controller.target(obs)
    assert controller.tracking_debt == 0
    controller.phase, controller.stable = 'push', False
    controller.target(obs)
    assert controller.tracking_debt == 0


def test_object_jump_discards_old_tracking_memory(controller, contact_target):
    controller.phase, controller.stable, controller.braking = 'push', True, False
    controller.target(observation(tip=[-.05, 0., -.275]))
    controller.tracking_debt = .03
    controller.target(observation(x=.15, tip=[-.05, 0., -.275]))
    assert controller.tracking_debt == 0 and len(controller.object_history) == 1


def test_braking_uses_closing_motion_and_expires_without_settling(controller, contact_target):
    controller.phase = 'push'
    controller.target(observation(x=.22))
    controller.target(observation(x=.23))
    assert controller.braking_active
    assert controller.event_counts['observed_closing_brake'] == 1
    for _ in range(12):
        controller.target(observation(x=.23))
    assert not controller.braking_active


def test_receding_or_stationary_object_does_not_trigger_predictive_brake(controller, contact_target):
    controller.phase = 'push'
    for x in (.24, .23, .22, .22):
        controller.target(observation(x=x))
    assert not controller.braking_active


def test_disabled_features_reproduce_frozen_controller_on_real_observations(controller):
    baseline = ReachableStrategyController(controller.model)
    disabled = ProgressRecoveryController(controller.model, tracking_memory=False, braking=False)
    with zipfile.ZipFile(ROOT / 'docs/evidence/strategy-v2/reachable-contact-geometry/trajectories.zip') as bundle:
        rows = [json.loads(line) for line in bundle.read('full/case_d/seed1/trajectory.jsonl').splitlines()]
    for row in rows:
        obs = np.array(row['observation_before'])
        np.testing.assert_array_equal(disabled.action(obs), baseline.action(obs))
        assert disabled.phase == baseline.phase
    assert disabled.retries > 0  # Equivalence includes actual recovery, not startup alone.


def test_new_controller_rejects_invalid_observations(controller):
    with pytest.raises(ValueError, match='finite 23-value'):
        controller.action(np.full(23, np.nan))


def test_tracking_memory_does_not_accumulate_before_productive_pushing(controller, contact_target):
    controller.phase, controller.stable, controller.braking = 'push', True, False
    for _ in range(100):
        controller.target(observation(tip=[-.05, 0., -.275]))
    assert controller.tracking_debt == 0


def test_brake_restores_joint_pose_instead_of_only_damping_velocity(controller):
    controller.model.opt.gravity[:] = 0  # Isolate position-restoring work.
    controller.braking_joints = np.zeros(7)
    obs = observation()
    obs[:7] = .01
    torque = controller._brake_action(obs)
    assert np.dot(torque, obs[:7] - controller.braking_joints) < 0
    assert np.isfinite(torque).all() and np.max(np.abs(torque)) <= 2
