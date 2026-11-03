from dataclasses import replace
import gymnasium as gym
import numpy as np
import pytest

from control.adaptation_schema import AdaptationSkill, parse, text, make_controller
from simulation.delay_shift import DelayedPusher
from simulation.environment import ShiftedPusher


def test_tagged_policy_is_strict_and_has_no_numeric_gain_or_code_surface():
    skill = AdaptationSkill(2, controller='recovery')
    assert parse(text(skill)) == skill
    for invalid in (text(skill).replace('version: 2', 'version: true'),
                    text(skill) + 'python: do_something\n',
                    text(skill).replace('braking: pose_hold', 'braking: arbitrary_python'),
                    text(skill).replace('version: 2', 'version: 2\nversion: 3'),
                    '!!python/object/apply:os.system [bad]',
                    text(AdaptationSkill()).replace('controller: original', 'controller: original\n  braking: pose_hold')):
        with pytest.raises(ValueError):
            parse(invalid)


def test_mid_task_delay_uses_actual_earlier_commands_without_resetting_to_zero():
    env = DelayedPusher(2, 3)
    try:
        env.reset(seed=0)
        applied = []
        for i in range(1, 7):
            env.step(np.full(7, i / 10))
            applied.append(env.last_applied_action[0])
        np.testing.assert_allclose(applied, [.1, .2, .3, .2, .3, .4])
    finally:
        env.close()


def test_constant_four_step_delay_exactly_preserves_existing_physics():
    old, new = ShiftedPusher('actuator_delay'), DelayedPusher(4, 0)
    try:
        np.testing.assert_array_equal(old.reset(seed=1)[0], new.reset(seed=1)[0])
        rng = np.random.default_rng(91)
        for _ in range(20):
            action = rng.uniform(-2, 2, 7)
            np.testing.assert_array_equal(old.step(action)[0], new.step(action)[0])
            np.testing.assert_array_equal(old.last_applied_action, new.last_applied_action)
    finally:
        old.close()
        new.close()


def test_recovery_policy_builds_independent_bounded_controller():
    env = gym.make('Pusher-v5')
    try:
        obs, _ = env.reset(seed=0)
        controller = make_controller(env.unwrapped.model, AdaptationSkill(2, controller='recovery'))
        action = controller.action(obs)
        assert action.shape == (7,) and np.isfinite(action).all() and max(abs(action)) <= 2
    finally:
        env.close()
