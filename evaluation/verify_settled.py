"""Verify increment 2 ablations from archived trajectories, without simulation."""
import hashlib
import json
from pathlib import Path
import zipfile

from evaluation.benchmark import ROOT, source_hash
from evaluation.heldout import verify_protocol
from evaluation.metrics import aggregate, score_episode
from evaluation.verify_recovery import text_hash_matches, verify as verify_increment1


DIRECTORY = ROOT / 'docs/evidence/recovery-increment2'


def verify(directory=DIRECTORY):
    spec, _, _, _ = verify_protocol()
    verify_increment1()
    directory = Path(directory)
    index = json.loads((directory / 'archive.json').read_text())
    for name, expected in index['sha256'].items():
        valid = (hashlib.sha256((directory / name).read_bytes()).hexdigest() == expected
                 if name.endswith('.zip') else text_hash_matches(directory / name, expected))
        if not valid:
            raise ValueError('Increment 2 evidence changed')
    manifest = json.loads((directory / 'manifest.json').read_text())
    report = json.loads((directory / 'report.json').read_text())
    baseline = ROOT / 'docs/evidence/recovery-v2/final/report.json'
    if (not text_hash_matches(baseline, manifest['baseline_report_sha256'])
            or manifest['scoring'] != spec or not report['protected_artifacts_unchanged']):
        raise ValueError('Comparison protocol differs')
    for label, result in json.loads(baseline.read_text())['controllers'].items():
        if result != report['controllers'][label]:
            raise ValueError('Reused baseline differs from original evidence')
    checked = 0
    with zipfile.ZipFile(directory / 'trajectories.zip') as bundle:
        for name, expected in manifest['source_sha256'].items():
            archived = bundle.read('source/' + name).decode('utf-8-sig').replace('\r\n', '\n')
            if hashlib.sha256(archived.encode()).hexdigest() != expected or source_hash(ROOT / name) != expected:
                raise ValueError('Measured source differs')
        for label in ('confirmed_recovery', 'settled_recovery'):
            result = report['controllers'][label]
            episodes = result['episodes']
            expected = {(s, seed) for s in ('nominal', 'high_mass', 'actuator_delay') for seed in range(5)}
            if len(episodes) != 15 or {(e['scenario'], e['seed']) for e in episodes} != expected:
                raise ValueError('Missing or duplicated episodes')
            measured = []
            for episode in episodes:
                path = f"{label}/{episode['scenario']}/seed{episode['seed']}/trajectory.jsonl"
                data = bundle.read(path)
                if hashlib.sha256(data).hexdigest() != episode['trajectory_sha256']:
                    raise ValueError('Trajectory differs')
                metrics = score_episode([json.loads(line) for line in data.splitlines()], spec)
                if any(episode[key] != value for key, value in metrics.items()):
                    raise ValueError('Episode score differs')
                measured.append({'scenario': episode['scenario'], **metrics})
                checked += 1
            if aggregate(measured) != result['aggregate']:
                raise ValueError('Aggregate differs')
            for scenario, expected in result['by_scenario'].items():
                if aggregate([e for e in measured if e['scenario'] == scenario]) != expected:
                    raise ValueError('Scenario aggregate differs')
    return {'verified': True, 'new_developer_episodes_rescored': checked,
            'reused_baseline_episodes_verified': 30, 'model_calls': 0, 'new_simulation_trials': 0}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
