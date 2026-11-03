import json
from pathlib import Path

import numpy as np
import pytest

from agent import adaptation_bridge as module
from agent.adaptation_bridge import AdaptationBridge
from control.adaptation_schema import AdaptationSkill, text
from control.response_recovery import ResponseRecoveryController
from control.progress_recovery import ProgressRecoveryController
from evaluation.benchmark import ROOT
from evaluation.metrics import aggregate
from evaluation.v3.final_evaluation import reserve_final, paired_intervals, wilson
from evaluation.v3.benchmark import spec
from tests.test_recovery import observation


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    directory = tmp_path / 'strategies/v3'
    directory.mkdir(parents=True)
    (directory / 'initial.yaml').write_text(text(AdaptationSkill()))
    monkeypatch.setattr(module, 'verify', lambda: (spec(), {}))
    return AdaptationBridge(tmp_path)


def test_full_baseline_is_required_before_revisions_without_spending_budget(bridge):
    for call in (lambda: bridge.save_candidate_strategy(text(AdaptationSkill(2, controller='recovery')), 'Observed sustained tracking errors.'),
                 lambda: bridge.evaluate_candidate('s0002')):
        with pytest.raises(ValueError, match='Evaluate initial'):
            call()
    assert not any(bridge.state['used'].values())


def test_agent_cannot_probe_validation_or_final_conditions(bridge):
    for identifier in ('v01', 'h01', '../heldout', 1000):
        with pytest.raises(ValueError, match='Only listed opaque development'):
            bridge.run_trial('initial', identifier)
    assert bridge.state['used']['trials'] == 0


def fake_evaluate(policy, split, output):
    output = Path(output)
    output.mkdir(parents=True)
    episodes = [{'condition_id': f'v{i+1:02d}', 'eligible': True, 'success': policy.controller == 'recovery' or i == 0,
                 'score': 90. if policy.controller == 'recovery' or i == 0 else 10.,
                 'final_error_xy_m': .01 if policy.controller == 'recovery' or i == 0 else .2,
                 'mean_squared_torque': .1, 'settled_time_fraction': .5, 'retries_used': 0,
                 'brake_activations': 0} for i in range(2)]
    import hashlib
    report = {'aggregate': aggregate(episodes), 'episodes': episodes,
              'policy_sha256': hashlib.sha256(text(policy).encode()).hexdigest()}
    (output / 'report.json').write_text(json.dumps(report))
    return report


def test_baseline_reuse_immutable_save_and_real_promotion_receipts(bridge, monkeypatch):
    monkeypatch.setattr(module, 'evaluate', fake_evaluate)
    baseline = bridge.evaluate_candidate('initial')
    again = bridge.evaluate_candidate('initial')
    assert again['reused'] and again['run_id'] == baseline['run_id']
    assert bridge.state['used']['evaluations'] == 1
    saved = bridge.save_candidate_strategy(text(AdaptationSkill(2, controller='recovery')), 'Observed approach tracking failure; select bounded recovery.')
    with pytest.raises(ValueError, match='immutable'):
        bridge.save_candidate_strategy(saved['policy'], 'Do not overwrite the original policy.')
    candidate = bridge.evaluate_candidate(saved['strategy_id'])
    assert bridge.promote_strategy(baseline['run_id'], candidate['run_id'])['accepted']
    assert AdaptationBridge(bridge.root).state['promoted'] == 's0002'
    assert bridge.state['used'] == {'evaluations': 2, 'trials': 0, 'candidates': 1}
    (bridge.directory / 'evaluations' / candidate['run_id'] / 'report.json').write_text('{}')
    with pytest.raises(ValueError, match='report changed'):
        bridge.promote_strategy(baseline['run_id'], candidate['run_id'])


def test_operation_lock_is_fail_closed_and_not_silently_deleted(bridge):
    path = bridge.directory / 'operation.lock'
    path.write_text('another process')
    with pytest.raises(FileExistsError):
        bridge.get_status()
    assert path.read_text() == 'another process'


def test_final_reservation_freezes_policies_and_refuses_repeat_access(tmp_path):
    path = tmp_path / 'finalized.json'
    first = reserve_final(path, {'original': AdaptationSkill(), 'agent': AdaptationSkill(2, controller='recovery')})
    with pytest.raises(FileExistsError):
        reserve_final(path, {'original': AdaptationSkill()})
    assert json.loads(path.read_text()) == first


def test_response_deterioration_latches_stabilization_without_physics_inputs(monkeypatch):
    import gymnasium as gym
    env = gym.make('Pusher-v5')
    def target(self, obs):
        self.step += 1
        self.stable = False  # Reproduce the old initial-response preference.
        self.command_stage = 'push'
        return self._record_target(np.array([0., 0., -.275]), 'push'), np.array([1., 0.])
    monkeypatch.setattr(ProgressRecoveryController, 'target', target)
    try:
        c = ResponseRecoveryController(env.unwrapped.model)
        c.command_stage, c.command_target = 'push', np.array([0., 0., -.275])
        for _ in range(20):
            c.target(observation(tip=[-.01, 0., -.275]))
        assert not c.stabilization_latched
        for _ in range(3):
            c.target(observation(tip=[-.2, 0., -.275]))
        assert c.stabilization_latched and c.stable
        c.target(observation(tip=[-.01, 0., -.275]))
        assert c.stable and c.event_counts['observed_response_deterioration'] == 1
    finally:
        env.close()


def test_three_sets_are_disjoint_and_final_delays_are_not_selection_delays():
    sets = spec()['splits']
    seeds = {k: {c['seed'] for c in rows} for k, rows in sets.items()}
    assert not (seeds['development'] & seeds['validation'] or seeds['validation'] & seeds['heldout'] or seeds['development'] & seeds['heldout'])
    assert not seeds['validation'] & {100, 101, 102, 103, 104}
    training = {c['delay_steps'] for k in ('development', 'validation') for c in sets[k]} - {0}
    final = {c['delay_steps'] for c in sets['heldout']} - {0}
    assert not training & final
    assert len(sets['heldout']) == 25 and len(sets['validation']) == 21


def test_uncertainty_has_valid_bounds_and_preserves_pairing():
    lo, hi = wilson(0, 5)
    assert 0 <= lo <= hi <= 1
    rows = [{'condition_id': str(i), 'success': True, 'final_error_xy_m': .01, 'mean_squared_torque': .1} for i in range(4)]
    conditions = [{'id': str(i), 'seed': i // 2} for i in range(4)]
    paired = paired_intervals({'episodes': rows}, {'episodes': rows}, conditions)
    assert paired['starting_seed_clusters'] == 2
    assert paired['metrics']['success']['paired_seed_cluster_bootstrap_95'] == [0., 0.]
