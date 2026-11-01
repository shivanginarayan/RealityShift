import json
from unittest.mock import Mock

import pytest

from agent import configure_strategy_trueforge, run_strategy_adaptation
from evaluation.strategy_ablation import stability_gate
from evaluation.v2 import activate as module
from evaluation.v2.benchmark import read_spec
from evaluation.v2 import benchmark
from evaluation.benchmark import source_hash


def blocked():
    raise ValueError('Developer stability gate not passed')


def test_no_trueforge_requests_before_stability_gate(monkeypatch):
    for target, call in ((configure_strategy_trueforge, configure_strategy_trueforge.configure),
                         (run_strategy_adaptation, run_strategy_adaptation.start)):
        network = Mock(side_effect=AssertionError('No service request allowed'))
        monkeypatch.setattr(target, 'request', network)
        monkeypatch.setattr(target, 'verify_v2', blocked)
        with pytest.raises(ValueError, match='stability'):
            call()
        network.assert_not_called()


def test_gate_requires_all_cases_and_actual_post_probe_retries():
    spec = read_spec()
    episodes = [{'case_id': case, 'seed': seed, 'success': True, 'eligible': True,
                 'strategy_events': [{'step': 100}]} for case, data in spec['cases'].items() for seed in data['seeds']]
    assert stability_gate(episodes, spec)['passed']
    for e in episodes:
        if e['case_id'] == 'case_d':
            e['strategy_events'] = []
    gate = stability_gate(episodes, spec)
    assert not gate['passed']
    assert not gate['checks']['case_d_successful_post_interruption_retry']
    assert not stability_gate(episodes[:-1], spec)['passed']


def test_activation_refuses_failed_gate_and_writes_no_freeze(tmp_path, monkeypatch):
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    (evidence / 'manifest.json').write_text(json.dumps({'spec': read_spec()}))
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'DIRECTORY', tmp_path / 'evaluation/v2')
    monkeypatch.setattr(module, 'verify_protocol', lambda: None)
    monkeypatch.setattr(module, 'verify', lambda *args, **kwargs: {'stability_passed': False})
    with pytest.raises(ValueError, match='stability gate failed'):
        module.activate(evidence)
    assert not (tmp_path / 'evaluation/v2/frozen.json').exists()


def test_activation_locks_code_and_gate_evidence_once(tmp_path, monkeypatch):
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    for name, value in [('manifest.json', {'spec': read_spec()}), ('archive.json', {}),
                        ('report.json', {}), ('stability.json', {'passed': True})]:
        (evidence / name).write_text(json.dumps(value))
    directory = tmp_path / 'evaluation/v2'
    directory.mkdir(parents=True)
    source = tmp_path / 'source.py'
    source.write_text('pass\n')
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'DIRECTORY', directory)
    monkeypatch.setattr(module, 'SOURCES', ['source.py'])
    monkeypatch.setattr(module, 'AGENT_SOURCES', [])
    monkeypatch.setattr(module, 'verify_protocol', lambda: None)
    monkeypatch.setattr(module, 'verify', lambda *args, **kwargs: {'stability_passed': True})
    lock = module.activate(evidence)
    assert 'evidence/stability.json' in lock['source_sha256']
    assert 'evidence/report.json' in lock['source_sha256']
    with pytest.raises(FileExistsError):
        module.activate(evidence)


def test_v2_freeze_rejects_changed_policy_or_gate_evidence(tmp_path, monkeypatch):
    spec = read_spec()
    directory = tmp_path / 'v2'
    directory.mkdir()
    policy, gate = tmp_path / 'policy.py', tmp_path / 'gate.json'
    policy.write_text('pass\n')
    gate.write_text('{"passed": true}')
    lock = {'source_sha256': {'policy.py': source_hash(policy)},
            'gate_path': 'gate.json', 'gate_sha256': source_hash(gate)}
    (directory / 'frozen.json').write_text(json.dumps(lock))
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    monkeypatch.setattr(benchmark, 'DIRECTORY', directory)
    monkeypatch.setattr(benchmark, 'verify_protocol', lambda: None)
    monkeypatch.setattr(benchmark, 'read_spec', lambda: spec)
    assert benchmark.verify_v2()[0] == spec
    policy.write_text('changed\n')
    with pytest.raises(ValueError, match='frozen artifact changed'):
        benchmark.verify_v2()
    policy.write_text('pass\n')
    gate.write_text('{"passed": false}')
    with pytest.raises(ValueError, match='gate evidence'):
        benchmark.verify_v2()
