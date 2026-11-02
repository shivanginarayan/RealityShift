from copy import deepcopy
import json
import pytest

from evaluation.benchmark import ROOT
from evaluation.progress_comparison import acceptance, verify


def baseline():
    return json.loads((ROOT / 'docs/evidence/strategy-v2/reachable-contact-geometry/report.json').read_text())['variants']['full']['episodes']


def test_acceptance_requires_more_successes_without_trading_away_old_successes():
    before = baseline()
    after = deepcopy(before)
    failures = [e for e in after if not e['success']]
    failures[0]['success'] = True
    assert acceptance({'baseline': before, 'full': after})['accepted']
    failures[1]['success'] = True
    next(e for e in after if e['success'] and e['case_id'] == 'case_a')['success'] = False
    checked = acceptance({'baseline': before, 'full': after})
    assert checked['checks']['more_successes']
    assert not checked['accepted']


def test_success_without_an_explicit_recovery_cannot_replace_recovery_evidence():
    before = baseline()
    after = deepcopy(before)
    next(e for e in after if not e['success'])['success'] = True
    for e in after:
        if e['case_id'] == 'case_d':
            e['strategy_events'] = []
    checked = acceptance({'baseline': before, 'full': after})
    assert not checked['checks']['case_d_recovery_nonregression']
    assert not checked['accepted']


@pytest.mark.parametrize('attempt', ['first', 'productive-contact'])
def test_all_progress_comparison_outcomes_rescore_from_archived_observations(attempt):
    result = verify(ROOT / 'docs/evidence/progress-recovery' / attempt)
    assert result['verified'] and result['episodes_rescored'] == 84
    assert result['model_calls'] == 0 and result['new_simulation_trials'] == 0
