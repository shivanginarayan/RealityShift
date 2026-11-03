from dataclasses import replace
import zipfile

import pytest

from control.adaptation_schema import parse
from evaluation.benchmark import ROOT
from evaluation.v3.evidence import verify, verify_development


@pytest.mark.parametrize('attempt', ['development-first', 'development-response'])
def test_every_v3_development_attempt_retains_all_outcomes_and_measured_sources(attempt):
    result = verify_development(ROOT / 'docs/evidence/adaptation-v3' / attempt)
    assert result['verified'] and result['episodes_rescored'] == 42
    assert result['model_calls'] == 0


def test_actual_v3_agent_search_and_one_shot_final_results_reproduce_offline():
    result = verify(ROOT / 'docs/evidence/adaptation-v3/experiment')
    assert result['verified'] and result['episodes_rescored'] == 271
    assert result['agent_evaluations'] == 2 and result['conventional_evaluations'] == 6
    assert result['final_evaluations'] == 4 and result['promoted'] == 's0002'
    assert result['model_calls'] == 0 and result['new_simulation_trials'] == 0


def test_actual_agent_and_developer_policies_isolate_the_approach_strategy_choice():
    with zipfile.ZipFile(ROOT / 'docs/evidence/adaptation-v3/experiment/trajectories.zip') as bundle:
        developer = parse(bundle.read('source/strategies/v3/developer.yaml').decode('utf-8-sig'))
        agent = parse(bundle.read('strategies/s0002.yaml').decode('utf-8-sig'))
    assert agent.approach == 'stabilized' and developer.approach == 'adaptive'
    assert replace(developer, version=agent.version, approach='stabilized') == agent
    assert parse((ROOT / 'strategies/v3/versions/s0002.yaml').read_text()) == agent
