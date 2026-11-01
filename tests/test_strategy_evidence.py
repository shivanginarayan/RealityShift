import json
from pathlib import Path
import zipfile

import numpy as np
import pytest

from evaluation.benchmark import ROOT
from evaluation.recovery_diagnosis import analyze
from evaluation.v2.evidence import verify


@pytest.mark.parametrize('run', ['first', 'response-probe', 'position-contact'])
def test_all_developer_ablation_outcomes_are_rescored(run):
    result = verify(ROOT / 'docs/evidence/strategy-v2' / run)
    assert result['verified'] and result['episodes_rescored'] == 84
    assert result['model_calls'] == 0 and result['new_simulation_trials'] == 0


def test_original_delay_failures_never_reached_pushing_and_replay_exactly():
    result = analyze()
    delayed = [e for e in result['episodes'] if e['controller'] == 'increment1' and e['scenario'] == 'actuator_delay']
    assert len(delayed) == 5
    assert all(not e['push_observed'] and 'approach_tracking_failure' in e['failure_categories']
               and 'control_oscillation' in e['failure_categories'] for e in delayed)
    lift = next(s for e in delayed if e['seed'] == 1 for s in e['segments'] if s['stage'] == 'recover_lift')
    assert lift['tip_target_min_m'] == pytest.approx(.25858, abs=1e-5)
    assert lift['saturated_torque_fraction'] > .97


def test_scripted_probes_are_recorded_and_contact_displacement_is_exact():
    directory = ROOT / 'docs/evidence/strategy-v2/response-probe'
    report = json.loads((directory / 'report.json').read_text())
    with zipfile.ZipFile(directory / 'trajectories.zip') as bundle:
        rows = [json.loads(line) for line in bundle.read('full/case_d/seed0/trajectory.jsonl').splitlines()]
    before = np.array(rows[88]['observation_after'])[17:19]
    displaced = np.array(rows[89]['observation_before'])[17:19]
    assert np.linalg.norm(displaced - before) == pytest.approx(.14)
    assert rows[89]['developer_intervention'] is True
    episode = next(e for e in report['variants']['full']['episodes'] if e['case_id'] == 'case_d' and e['seed'] == 0)
    assert episode['developer_intervention']['step'] == 90
