import gymnasium as gym
import mujoco
import numpy as np
import pytest

from control.reachable_recovery import ReachableStrategyController
from tests.test_recovery import observation


@pytest.fixture
def controller():
    env = gym.make('Pusher-v5')
    try:
        yield ReachableStrategyController(env.unwrapped.model)
    finally:
        env.close()


def test_planning_is_bounded_and_never_selects_a_push_away_from_goal(controller):
    env = gym.make('Pusher-v5')
    try:
        obs, _ = env.reset(seed=1)
        plan = controller.choose_contact_plan(obs)
        assert controller.plan_attempts <= 45
        assert plan is not None and plan.max_residual <= .025
        force = obs[17:19] - plan.contact[:2]
        goal = obs[20:22] - obs[17:19]
        assert np.dot(force, goal) / (np.linalg.norm(force) * np.linalg.norm(goal)) >= .499999
        assert obs[19] <= plan.contact[2] <= obs[19] + .080001
        controller.kinematics.qpos[:7] = plan.contact_joints
        mujoco.mj_kinematics(controller.model, controller.kinematics)
        axis = controller.kinematics.xmat[controller.tip_id].reshape(3, 3)[:, 1]
        assert abs(np.dot(axis, np.r_[force / np.linalg.norm(force), 0.])) <= .3
        assert abs(axis[2]) <= .3
        assert np.min(controller.table_clearances()) >= -.002
        object_geom = int(controller.model.body_geomadr[controller.model.body('object').id])
        gap = min(mujoco.mj_geomDistance(controller.model, controller.kinematics, int(g), object_geom, 1., None)
                  for g in controller.robot_geoms)
        assert -.02 <= gap <= .03
    finally:
        env.close()


def test_no_feasible_plan_stops_instead_of_repeating_target(controller):
    obs = observation(x=3., tip=[0., 0., -.16])
    controller.current_observation = obs
    controller._transition('reposition')
    assert controller.phase == 'exhausted'
    assert controller.plan_attempts == 45
    assert controller.event_counts['no_feasible_contact_plan'] == 1
    assert controller.target(obs)[0] is None


def test_observed_object_jump_starts_immediate_reacquisition(controller):
    controller.phase = 'push'
    controller.probe_finished = True
    controller.probe_responded = True
    first = observation()
    controller.target(first)
    shifted = first.copy()
    shifted[18] = .14
    controller.target(shifted)
    assert controller.phase in ('stabilize', 'reacquire')
    assert controller.retries == 1
    assert controller.strategy_events[0]['reason'] == 'lost_contact'
    assert controller.strategy_events[0]['step'] == 2


def test_responsive_nominal_contact_keeps_the_original_pushing_law(controller):
    controller.phase = 'lower'
    controller.probe_finished = True
    controller.probe_responded = True
    controller.stable = False
    controller.target(observation(tip=[-.09, 0., -.275]))
    assert controller.phase == 'push' and not controller.stable


def test_reachable_lower_arrival_uses_selected_plan(controller):
    env = gym.make('Pusher-v5')
    try:
        obs, _ = env.reset(seed=1)
        controller.plan = controller.choose_contact_plan(obs)
        controller.phase = 'correct_lower'
        controller.recovery_started = 0
        controller.retries = 1
        controller.probe_finished = True
        controller.stable = True
        obs[14:17] = controller.plan.contact
        for _ in range(3):
            controller.target(obs)
        assert controller.phase == 'push'
    finally:
        env.close()


def test_horizontal_route_is_used_only_when_it_clears_the_object():
    policy = ReachableStrategyController
    obj = np.array([0., 0., -.275])
    assert policy.clear_horizontal_path(np.array([-.1, -.14, -.275]), np.array([-.09, 0., -.275]), obj)
    assert not policy.clear_horizontal_path(np.array([.1, 0., -.275]), np.array([-.09, 0., -.275]), obj)


def test_contact_reference_keeps_the_orientation_aware_solution(controller):
    controller.reference = np.arange(7, dtype=float) / 10
    original = controller.reference.copy()
    controller.command_stage = 'correct_push'
    controller._recovery_reference(observation(), np.array([0., 0., -.275]))
    np.testing.assert_array_equal(controller.reference, original)


def test_horizontal_reacquisition_timeout_cannot_create_unbounded_retries(controller):
    env = gym.make('Pusher-v5')
    try:
        obs, _ = env.reset(seed=1)
        controller.plan = controller.choose_contact_plan(obs)
        controller.phase = 'reacquire'
        controller.recovery_started = 0
        controller.retries = 1
        controller.probe_finished = True
        # No observations move toward the chosen target.
        obs[14:17] = [-.6, .6, 0.]
        for _ in range(600):
            controller.target(obs)
        assert controller.phase == 'exhausted' and controller.retries == 2
    finally:
        env.close()


def test_table_clearance_matches_real_nominal_collision_geometry(controller):
    import json
    from pathlib import Path
    root = Path(__file__).parents[1]
    fixture = json.loads((root / 'docs/evidence/reachable-recovery/table-collision-replay.json').read_text())
    controller.kinematics.qpos[:7] = fixture['nominal_joints']
    mujoco.mj_forward(controller.model, controller.kinematics)
    clearances = controller.table_clearances()
    assert min(clearances) == pytest.approx(-.06831194, abs=1e-6)
    # Decorative non-colliding arm meshes must not invent impossible obstacles.
    assert set(controller.robot_geoms) == {13, 14, 15}
    contacts = [contact.dist for contact in controller.kinematics.contact
                if contact.geom1 == 0 and contact.geom2 in controller.robot_geoms]
    assert min(clearances) == pytest.approx(min(contacts), abs=1e-6)
