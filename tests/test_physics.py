import numpy as np
import pytest

from simulation.delay import ActionDelay
from simulation.environment import ShiftedPusher
from simulation.nominal import run_episode


def test_delay_has_exact_latency_and_clears_on_reset():
    delay = ActionDelay(2, (1,))
    np.testing.assert_array_equal(delay.apply([1]), [0])
    np.testing.assert_array_equal(delay.apply([2]), [0])
    np.testing.assert_array_equal(delay.apply([3]), [1])
    delay.reset()
    np.testing.assert_array_equal(delay.apply([4]), [0])
    np.testing.assert_array_equal(ActionDelay(0, (1,)).apply([5]), [5])


@pytest.mark.parametrize("steps", [-1, 1.5, True, 101])
def test_invalid_delay_rejected(steps):
    with pytest.raises(ValueError):
        ActionDelay(steps, (7,))


def test_mass_is_scaled_without_changing_seeded_initial_state():
    nominal, shifted = ShiftedPusher(), ShiftedPusher("high_mass")
    try:
        baseline, _ = nominal.reset(seed=42)
        changed, _ = shifted.reset(seed=42)
        np.testing.assert_array_equal(baseline, changed)
        body = shifted.unwrapped.model.body("object").id
        assert shifted.actual_mass == pytest.approx(nominal.actual_mass * 10000)
        np.testing.assert_allclose(shifted.unwrapped.model.body_inertia[body],
                                   nominal.unwrapped.model.body_inertia[body] * 10000)
        assert np.linalg.norm(shifted.unwrapped.model.body_subtreemass -
                              nominal.unwrapped.model.body_subtreemass) > 0
        shifted.reset(seed=42)
        assert shifted.actual_mass == pytest.approx(nominal.actual_mass * 10000)
    finally:
        nominal.close()
        shifted.close()


def test_environment_reset_clears_queued_commands_and_rejects_invalid_actions():
    env = ShiftedPusher("actuator_delay")
    try:
        original, _ = env.reset(seed=42)
        for _ in range(5):
            env.step(np.ones(7))
        np.testing.assert_array_equal(env.last_applied_action, np.ones(7))
        repeated, info = env.reset(seed=42)
        np.testing.assert_array_equal(original, repeated)
        env.step(np.ones(7))
        np.testing.assert_array_equal(env.last_applied_action, np.zeros(7))
        assert "delay_steps" not in info
        for action in (np.full(7, np.nan), np.zeros(6), np.full(7, 3)):
            with pytest.raises(ValueError):
                env.step(action)
    finally:
        env.close()


def test_shifted_episode_is_repeatable(tmp_path):
    first = run_episode(42, tmp_path / "first", "actuator_delay")
    second = run_episode(42, tmp_path / "second", "actuator_delay")
    assert first["trajectory_sha256"] == second["trajectory_sha256"]
    assert first["success"] == second["success"]
    assert first["developer_physics_manifest"]["delay_seconds"] == pytest.approx(.2)
