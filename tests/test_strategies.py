from dataclasses import replace
import json

import gymnasium as gym
import numpy as np
import pytest

from agent.strategy_diagnostics import diagnose
from control.strategies import StrategyController, StrategyFailureDetector
from control.strategy_schema import StrategySkill, parse_strategy, strategy_text
from tests.test_recovery import observation


@pytest.fixture
def controller():
    env = gym.make('Pusher-v5')
    try:
        yield StrategyController(env.unwrapped.model)
    finally:
        env.close()


def test_strategy_schema_round_trip_and_closed_fields():
    text = strategy_text(StrategySkill())
    assert parse_strategy(text) == StrategySkill()
    for invalid in (text + 'shell: yes\n', text.replace('adaptive', 'shell'),
                    text.replace('version: 1', 'version: true'),
                    text.replace('approach: adaptive', 'approach: adaptive\n  approach: direct'),
                    text.replace('stall: controlled_repush', 'stall: 2'), 'a' * 4097):
        with pytest.raises(ValueError):
            parse_strategy(invalid)


def test_strategies_are_distinct_and_enum_choices_change_transitions(controller):
    obs = observation()
    controller._begin('stall', obs)
    assert controller.phase == 'repush_backoff'
    for _ in range(3):
        controller.target(observation(tip=[-.07, 0., -.275]))
    assert controller.phase == 'repush'
    target, _ = controller.target(obs)
    assert np.linalg.norm(target - obs[14:17]) <= .008000001
    controller.target(observation(.02))
    assert controller.phase == 'push'
    controller.strategy = replace(controller.strategy, stall='reapproach')
    controller._begin('stall', obs)
    assert controller.phase == 'stabilize'


def test_overshoot_repositions_on_current_side_and_corrects(controller):
    obs = observation(.36)
    controller._begin('overshoot', obs)
    for _ in range(12):
        controller.target(obs)
    assert controller.phase == 'recover_lift'
    raised = observation(.36, tip=[.335, 0., -.16])
    for _ in range(3):
        controller.target(raised)
    assert controller.phase == 'reposition'
    assert controller.snapshot_target[0] > .36  # opposite side after crossing goal
    at_target = observation(.36, tip=controller.snapshot_target)
    for _ in range(3):
        controller.target(at_target)
    assert controller.phase == 'correct_lower'
    for _ in range(3):
        controller.target(observation(.36, tip=[.45, 0., -.275]))
    assert controller.phase == 'correct_push'


def test_contact_failure_selects_stabilized_reacquisition(controller):
    controller._begin('lost_contact', observation())
    assert controller.stable and controller.phase == 'stabilize'
    assert controller.strategy_events[0]['reason'] == 'lost_contact'


def test_adaptive_switch_uses_observations_and_target_error(controller):
    controller.phase = 'lower'
    for i in range(40):
        obs = observation(tip=[-.4, .3, -.16])
        obs[7:14] = 1 if i % 2 else -1
        controller.target(obs)
    assert controller.stable
    assert controller.event_counts['observed_tracking_oscillation'] == 1


def test_fast_goal_crossing_does_not_require_a_sample_at_the_goal():
    detector = StrategyFailureDetector()
    assert detector.update(observation(.1)) is None
    assert detector.update(observation(.4)) == 'overshoot'
    detector.reset()
    detector.update(observation(.1))
    lateral = observation(.4)
    lateral[18] = .3
    assert detector.update(lateral) != 'overshoot'


def test_adaptive_startup_uses_observed_response_not_case_id(controller):
    initial = observation()
    for step in range(1, 8):
        controller.target(initial)
    assert controller.stable and not controller.probe_responded
    env = gym.make('Pusher-v5')
    try:
        responsive = StrategyController(env.unwrapped.model)
        for step in range(1, 8):
            obs = initial.copy()
            obs[7] = 0 if step == 1 else .2
            responsive.target(obs)
        assert not responsive.stable and responsive.probe_responded
    finally:
        env.close()


def test_retries_and_unreachable_targets_are_bounded(controller):
    obs = observation(tip=[-.6, .6, 0.])
    for _ in range(700):
        controller.target(obs)
    assert controller.phase == 'exhausted'
    assert controller.retries == 2


def test_diagnostics_separate_noncontact_from_pushing_and_oscillation():
    def history(stage, tip):
        rows = []
        for i in range(40):
            obs = observation(tip=tip)
            obs[7:14] = 1 if i % 2 else -1
            rows.append({'stage': stage, 'target': [0, 0, -.16], 'observation': obs,
                         'issued_action': [2 if i % 2 else -2] * 7})
        return rows
    first = diagnose(history('approach', [-.4, .2, -.16]))
    assert first['failure_categories'] == ['approach_tracking_failure', 'control_oscillation']
    assert not first['push_observed']
    assert 'contact_acquisition_failure' in diagnose(history('push', [-.4, .2, -.16]))['failure_categories']
    assert 'pushing_or_settling_failure' in diagnose(history('push', [-.025, 0., -.275]))['failure_categories']
    serialized = json.dumps(first)
    for forbidden in ('mass_scale', 'delay_steps', 'applied_action', 'physics_manifest'):
        assert forbidden not in serialized


def test_strategy_actions_are_finite_bounded_and_do_not_change_live_state():
    env = gym.make('Pusher-v5')
    try:
        obs, _ = env.reset(seed=0)
        before = env.unwrapped.data.qpos.copy()
        for approach in ('direct', 'stabilized', 'adaptive'):
            controller = StrategyController(env.unwrapped.model, StrategySkill(approach=approach))
            action = controller.action(obs)
            assert action.shape == (7,) and np.isfinite(action).all() and np.max(np.abs(action)) <= 2
        np.testing.assert_array_equal(before, env.unwrapped.data.qpos)
    finally:
        env.close()


def test_repush_waypoint_advances_but_lead_is_bounded(controller):
    obs = observation()
    controller.phase = 'repush'
    controller.recovery_started = 0
    controller.repush_error = .3
    controller.probe_finished = True
    targets = [controller.target(obs)[0] for _ in range(4)]
    assert np.linalg.norm(targets[-1] - obs[14:17]) > np.linalg.norm(targets[0] - obs[14:17])
    assert np.linalg.norm(targets[-1] - obs[14:17]) <= .04
    assert all(np.linalg.norm(b-a) <= .008000001 for a,b in zip(targets, targets[1:]))


def test_recovery_ik_does_not_claim_an_infeasible_target_is_reached(controller):
    import zipfile
    from pathlib import Path
    import mujoco
    # Exact failed opposite-side target from the preserved second comparison.
    root = Path(__file__).parents[1]
    with zipfile.ZipFile(root / 'docs/evidence/strategy-v2/response-probe/trajectories.zip') as bundle:
        rows = [json.loads(line) for line in bundle.read('full/case_f/seed0/trajectory.jsonl').splitlines()]
    row = next(r for r in rows if r['command_stage'] == 'reposition')
    obs, target = np.array(row['observation_before']), np.array(row['command_target'])
    controller._recovery_reference(obs, target)
    controller.kinematics.qpos[:7] = controller.reference
    mujoco.mj_kinematics(controller.model, controller.kinematics)
    residual = np.linalg.norm(controller.kinematics.xpos[controller.tip_id] - target)
    # Relaxing orientation alone does not fix this nominal-model feasibility
    # failure. Keep the failed case visible rather than asserting recovery.
    assert residual > .04
