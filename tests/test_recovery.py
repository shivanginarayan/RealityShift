import json

import gymnasium as gym
import numpy as np
import pytest

from agent.recovery_diagnostics import summarize_observations
from control.recovery import FailureDetector, RecoveryConfig, RecoveryController


def observation(x=0., tip=None, goal=.3):
    obs = np.zeros(23)
    obs[14:17] = tip if tip is not None else [x - .025, 0., -.275]
    obs[17:20] = [x, 0., -.275]
    obs[20:23] = [goal, 0., -.323]
    return obs


def test_stall_requires_window_and_is_resettable():
    detector = FailureDetector()
    for _ in range(23):
        assert detector.update(observation()) is None
    assert detector.update(observation()) == "stall"
    detector.reset()
    assert detector.update(observation()) is None


def test_progress_and_goal_settling_do_not_trigger():
    for samples in ([observation(x=i * .003) for i in range(70)],
                    [observation(x=.28) for _ in range(60)]):
        detector = FailureDetector()
        assert all(detector.update(obs) is None for obs in samples)


def test_contact_loss_debounces_and_requires_lack_of_progress():
    detector = FailureDetector()
    far = observation(tip=[-.3, 0., -.16])
    detector.update(observation())  # establish contact proximity first
    for _ in range(7):
        assert detector.update(far) is None
    assert detector.update(far) == "lost_contact"
    detector.reset()
    detector.update(observation())
    for i in range(15):
        assert detector.update(observation(i * .004, tip=[-.3, 0., -.16])) is None
    detector.reset()
    detector.update(observation())
    for _ in range(7):
        detector.update(far)
    detector.update(observation())
    assert detector.update(far) is None


def test_initial_separation_is_acquisition_not_lost_contact():
    detector = FailureDetector()
    far = observation(tip=[-.3, 0., -.16])
    # The old implementation falsely interrupted an otherwise successful run.
    for _ in range(12):
        assert detector.update(far) is None
    assert detector.update(observation()) is None
    detector.reset()
    for _ in range(47):
        assert detector.update(far) is None
    assert detector.update(far) == "contact_not_acquired"


def test_stall_window_starts_after_contact_acquisition():
    detector = FailureDetector()
    for _ in range(20):
        assert detector.update(observation(tip=[-.3, 0., -.16])) is None
    for _ in range(23):
        assert detector.update(observation()) is None
    assert detector.update(observation()) == "stall"


def test_overshoot_requires_near_goal_crossing_and_error_growth():
    detector = FailureDetector()
    for x in (0., .2, .27, .31, .34):
        assert detector.update(observation(x)) is None
    assert detector.update(observation(.36)) == "overshoot"
    detector.reset()
    # Lateral drift near goal without crossing the goal plane is not overshoot.
    detector.update(observation(.27))
    obs = observation(.27)
    obs[18] = .1
    assert detector.update(obs) != "overshoot"


@pytest.fixture
def controller():
    env = gym.make("Pusher-v5")
    try:
        yield RecoveryController(env.unwrapped.model)
    finally:
        env.close()


def test_stall_lifts_reapproaches_lowers_and_retries(controller):
    controller.phase = "push"
    obs = observation()
    for _ in range(24):
        controller.target(obs)
    assert controller.phase == "recover_brake"
    assert controller.retries == 1
    for _ in range(controller.config.brake_steps):
        controller.target(obs)
    assert controller.phase == "recover_lift"
    raised_tip = observation(tip=[-.025, 0., controller.skill.approach_height])
    controller.target(raised_tip)
    assert controller.phase == "recover_reapproach"
    behind_raised = observation(tip=[-.09, 0., controller.skill.approach_height])
    controller.target(behind_raised)
    assert controller.phase == "recover_lower"
    controller.target(observation(tip=[-.09, 0., -.275]))
    assert controller.phase == "push"
    assert controller.detector.update(obs) is None  # stale stall window was cleared


@pytest.mark.parametrize("reason", ["lost_contact", "overshoot"])
def test_other_failures_enter_same_bounded_recovery(controller, reason):
    controller.phase = "push"
    samples = ([observation()] + [observation(tip=[-.3, 0., -.16])] * 8 if reason == "lost_contact"
               else [observation(x) for x in (0., .27, .36)])
    for obs in samples:
        controller.target(obs)
    assert controller.phase == "recover_brake"
    assert controller.events[0]["reason"] == reason


def test_unreachable_approach_terminates_with_bounded_retries(controller):
    obs = observation(tip=[-.6, .6, 0.])
    for _ in range(300):
        controller.target(obs)
    assert controller.phase == "exhausted"
    assert controller.retries == controller.config.max_retries
    assert len(controller.events) <= 16
    before = controller.retries
    for _ in range(50):
        assert controller.target(obs)[0] is None
    assert controller.retries == before
    action = controller.action(obs)
    assert np.isfinite(action).all() and np.max(np.abs(action)) <= 2


def test_total_recovery_timeout_even_if_individual_phases_are_not_expired(controller):
    controller.config = RecoveryConfig(recovery_timeout=5, phase_timeout=35)
    controller._recover("stall", observation())
    for _ in range(5):
        controller.target(observation())
    assert controller.retries == 2
    assert controller.event_counts["recovery_timeout"] == 1


def test_hold_has_fixed_target_and_recovers_on_goal_escape(controller):
    controller.phase = "push"
    target, _ = controller.target(observation(.28))
    changed_tip = observation(.28, tip=[.2, .01, -.27])
    np.testing.assert_array_equal(controller.target(changed_tip)[0], target)
    controller.target(observation(.22))
    assert controller.phase == "recover_brake"
    assert controller.events[0]["reason"] == "goal_escape"


def test_action_is_finite_bounded_and_does_not_touch_live_state():
    env = gym.make("Pusher-v5")
    try:
        obs, _ = env.reset(seed=0)
        controller = RecoveryController(env.unwrapped.model)
        before = env.unwrapped.data.qpos.copy()
        action = controller.action(obs)
        np.testing.assert_array_equal(env.unwrapped.data.qpos, before)
        assert action.shape == (7,)
        assert np.isfinite(action).all() and np.max(np.abs(action)) <= 2
    finally:
        env.close()


def test_same_observation_sequence_produces_identical_actions():
    env = gym.make("Pusher-v5")
    try:
        obs, _ = env.reset(seed=0)
        first = RecoveryController(env.unwrapped.model)
        second = RecoveryController(env.unwrapped.model)
        for _ in range(4):
            np.testing.assert_array_equal(first.action(obs), second.action(obs))
            assert first.phase == second.phase
    finally:
        env.close()


@pytest.mark.parametrize("bad", [np.zeros(22), np.full(23, np.nan)])
def test_invalid_observations_rejected(controller, bad):
    with pytest.raises(ValueError):
        controller.action(bad)


def test_compact_diagnostics_no_hidden_fields_and_no_duplicate_stall_spam():
    obs = [observation().tolist()] * 300
    result = summarize_observations(obs, ["push"] * 300)
    assert result["failure_hypotheses"] == {"stall": 1}
    assert result["examples"][0]["step"] == 24
    text = json.dumps(result)
    assert len(text) < 2000
    for forbidden in ("mass", "delay", "applied_action", "model", "manifest"):
        assert forbidden not in text
    with pytest.raises(ValueError):
        summarize_observations(obs, ["push"])


@pytest.mark.parametrize("kwargs", [{"max_retries": 0}, {"window": True}, {"contact_gap": float("nan")}])
def test_policy_config_is_bounded(kwargs):
    with pytest.raises(ValueError):
        RecoveryConfig(**kwargs)
