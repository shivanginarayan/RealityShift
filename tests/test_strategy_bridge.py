import hashlib
import json
from pathlib import Path

import pytest

from agent import strategy_bridge as module
from agent.strategy_bridge import StrategyBridge
from control.strategy_schema import StrategySkill, load_strategy, strategy_text
from evaluation.v2.benchmark import read_spec


@pytest.fixture
def bridge(tmp_path):
    (tmp_path / 'strategies/v2').mkdir(parents=True)
    (tmp_path / 'strategies/v2/initial.yaml').write_text(strategy_text(StrategySkill()))
    # A sentinel representing the old experiment must never be touched.
    (tmp_path / '.runtime/bridge').mkdir(parents=True)
    (tmp_path / '.runtime/bridge/state.json').write_text('original-v1-sentinel')
    return StrategyBridge(tmp_path)


def enable(monkeypatch):
    monkeypatch.setattr(module, 'verify_v2', lambda: (read_spec(), {}))


def test_unstable_gate_blocks_all_experiment_mutations_without_spending(bridge, monkeypatch):
    def blocked():
        raise ValueError('Developer stability gate has not passed')
    monkeypatch.setattr(module, 'verify_v2', blocked)
    assert bridge.get_status()['enabled'] is False
    for call in (lambda: bridge.run_trial('initial', 'case_a', 0),
                 lambda: bridge.evaluate_candidate('initial'),
                 lambda: bridge.save_candidate_strategy(strategy_text(StrategySkill(2)), 'An observed failure hypothesis.'),
                 lambda: bridge.promote_strategy('x', 'y')):
        with pytest.raises(ValueError, match='stability'):
            call()
    assert bridge.get_status()['remaining'] == {'evaluations': 6, 'trials': 12, 'candidates': 4}
    assert (bridge.root / '.runtime/bridge/state.json').read_text() == 'original-v1-sentinel'


def test_schema_paths_and_duplicate_versions_are_rejected(bridge, monkeypatch):
    enable(monkeypatch)
    for identifier in ('../x', 's0002.yaml', 'v0002', 's2', 's0002/../x'):
        with pytest.raises(ValueError):
            bridge._strategy(identifier)
    text = strategy_text(StrategySkill(2, stall='reapproach'))
    assert bridge.save_candidate_strategy(text, 'Test strategy based on observed stall feedback.')['strategy_id'] == 's0002'
    assert 'controlled_repush' in bridge.get_strategy_diff('s0002')['diff']
    with pytest.raises(ValueError, match='already exists'):
        bridge.save_candidate_strategy(text, 'Test strategy based on observed stall feedback.')
    assert bridge.get_status()['remaining']['candidates'] == 3
    assert StrategyBridge(bridge.root).get_status()['remaining']['candidates'] == 3


def test_invalid_cases_and_heldout_seeds_do_not_spend_budget(bridge, monkeypatch):
    enable(monkeypatch)
    for case, seed in [('high_mass', 0), ('case_a', 100), ('case_a', True), ('case_d', 4)]:
        with pytest.raises(ValueError):
            bridge.run_trial('initial', case, seed)
    assert bridge.get_status()['remaining']['trials'] == 12


def test_v2_budget_persists_and_busy_lock_prevents_concurrent_operation(bridge, monkeypatch):
    enable(monkeypatch)
    with bridge._transaction():
        bridge.state['used']['evaluations'] = 6
        bridge._audit('test_exhausted')
        with pytest.raises(ValueError, match='reserved'):
            StrategyBridge(bridge.root).get_status()
    restarted = StrategyBridge(bridge.root)
    with pytest.raises(ValueError, match='budget exhausted'):
        restarted.evaluate_candidate('initial')
    assert restarted.get_status()['remaining']['evaluations'] == 0


def test_real_trial_response_projection_filters_hidden_metadata(bridge, monkeypatch):
    enable(monkeypatch)
    def fake_run(*args):
        return {'case_id': 'case_c', 'seed': 0, 'eligible': True, 'violations': [], 'success': False,
                'score': 0., 'diagnostics': {'schema': 'strategy_diagnostics_v2', 'failure_categories': ['approach_tracking_failure']},
                'scenario': 'actuator_delay', 'developer_intervention': 'hidden', 'applied_action': [1],
                'trajectory_sha256': 'hidden', 'developer_physics_manifest': {'delay_steps': 4}}
    monkeypatch.setattr(module, 'run_episode', fake_run)
    result = bridge.run_trial('initial', 'case_c', 0)
    text = json.dumps(result)
    for forbidden in ('actuator_delay', 'delay_steps', 'physics', 'applied_action', 'developer_intervention', 'trajectory_sha256'):
        assert forbidden not in text
    assert 'approach_tracking_failure' in text and len(text) < 14000


def test_promotion_requires_real_hash_verified_reports_and_skills(bridge, monkeypatch):
    enable(monkeypatch)
    bridge.save_candidate_strategy(strategy_text(StrategySkill(2)), 'A measured behavioral strategy hypothesis.')
    def fake_evaluate(path, output):
        output.mkdir(parents=True)
        skill = load_strategy(path)
        report = {'strategy_sha256': hashlib.sha256(strategy_text(skill).encode()).hexdigest(),
                  'aggregate': {'eligible': True, 'rank': [skill.version, -.01, -1], 'score': skill.version},
                  'episodes': []}
        (output / 'report.json').write_text(json.dumps(report))
        return report
    monkeypatch.setattr(module, 'evaluate', fake_evaluate)
    with pytest.raises(ValueError, match='completed'):
        bridge.promote_strategy('fake', 'fake2')
    before = bridge.evaluate_candidate('initial')['run_id']
    after = bridge.evaluate_candidate('s0002')['run_id']
    assert bridge.promote_strategy(before, after)['accepted']
    path = bridge.directory / 'evaluations' / after / 'report.json'
    path.write_text('{}')
    with pytest.raises(ValueError, match='changed'):
        bridge.promote_strategy(before, after)


def test_corrupted_budget_state_is_not_reset(bridge):
    (bridge.directory / 'state.json').write_text('{"protocol": 1}')
    with pytest.raises(ValueError, match='refusing budget reset'):
        StrategyBridge(bridge.root)


def test_changed_loaded_sources_block_tools_before_spending(bridge, monkeypatch):
    monkeypatch.setattr(module, 'source_hash', lambda path: 'changed')
    with pytest.raises(ValueError, match='restart the strategy server'):
        bridge.get_status()
    assert bridge.state['used'] == {'evaluations': 0, 'trials': 0, 'candidates': 0}


def test_aggregate_improvement_cannot_hide_nominal_regression(bridge, monkeypatch):
    enable(monkeypatch)
    bridge.save_candidate_strategy(strategy_text(StrategySkill(2)), 'Test a measured strategy revision with a regression.')
    def evaluate(path, output):
        output.mkdir(parents=True)
        skill = load_strategy(path)
        candidate = skill.version == 2
        report = {'strategy_sha256': hashlib.sha256(strategy_text(skill).encode()).hexdigest(),
                  'aggregate': {'eligible': True, 'rank': [2 if candidate else 1], 'score': 80 if candidate else 50},
                  'episodes': [{'case_id': 'case_a', 'seed': 0, 'success': not candidate},
                               {'case_id': 'case_b', 'seed': 0, 'success': candidate}]}
        (output / 'report.json').write_text(json.dumps(report))
        return report
    monkeypatch.setattr(module, 'evaluate', evaluate)
    initial = bridge.evaluate_candidate('initial')['run_id']
    candidate = bridge.evaluate_candidate('s0002')['run_id']
    result = bridge.promote_strategy(initial, candidate)
    assert not result['accepted'] and not result['case_and_recovery_nonregression']
    assert result['promoted'] == 'initial'
