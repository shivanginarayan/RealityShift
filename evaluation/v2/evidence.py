"""Package/re-score developer strategy ablations; retain every measured attempt."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from evaluation.benchmark import ROOT, source_hash
from evaluation.metrics import aggregate, score_episode
from evaluation.strategy_ablation import stability_gate
from evaluation.verify_recovery import text_hash_matches


def package(origin, destination):
    origin, destination = Path(origin), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name in ('manifest.json', 'report.json', 'stability.json'):
        shutil.copyfile(origin / name, destination / name)
    manifest = json.loads((destination / 'manifest.json').read_text())
    with zipfile.ZipFile(destination / 'trajectories.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        paths = sorted(origin.glob('*/*/seed*/trajectory.jsonl'))
        if len(paths) != 84:
            raise ValueError('Expected all 84 ablation trajectories')
        for path in paths:
            bundle.write(path, path.relative_to(origin).as_posix())
        for name in manifest['source_sha256']:
            if source_hash(ROOT / name) != manifest['source_sha256'][name]:
                raise ValueError('Cannot snapshot a different measured source')
            bundle.write(ROOT / name, 'source/' + name)
    index = {'episodes': 84, 'authorship': 'developer', 'sha256': {
        name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
        for name in ('manifest.json', 'report.json', 'stability.json', 'trajectories.zip')}}
    (destination / 'archive.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')


def verify(directory, require_current=False):
    directory = Path(directory)
    index = json.loads((directory / 'archive.json').read_text())
    for name, expected in index['sha256'].items():
        valid = (hashlib.sha256((directory / name).read_bytes()).hexdigest() == expected
                 if name.endswith('.zip') else text_hash_matches(directory / name, expected))
        if not valid:
            raise ValueError('Strategy evidence changed')
    manifest = json.loads((directory / 'manifest.json').read_text())
    report = json.loads((directory / 'report.json').read_text())
    if (set(report['variants']) != {'full', 'without_stabilization', 'without_repush', 'without_correction'}
            or report.get('protected_artifacts_unchanged') is not True):
        raise ValueError('Incomplete ablation or failed preservation check')
    spec = manifest['spec']
    expected = {(case, seed) for case, data in spec['cases'].items() for seed in data['seeds']}
    checked = 0
    with zipfile.ZipFile(directory / 'trajectories.zip') as bundle:
        for name, digest in manifest['source_sha256'].items():
            raw = bundle.read('source/' + name).decode('utf-8-sig').replace('\r\n', '\n')
            if hashlib.sha256(raw.encode()).hexdigest() != digest:
                raise ValueError('Archived measured source differs')
            if require_current and source_hash(ROOT / name) != digest:
                raise ValueError('Current source differs from stability experiment')
        for label, variant in report['variants'].items():
            episodes = variant['episodes']
            if len(episodes) != len(expected) or {(e['case_id'], e['seed']) for e in episodes} != expected:
                raise ValueError('Missing or duplicate strategy episodes')
            measured = []
            for e in episodes:
                raw = bundle.read(f"{label}/{e['case_id']}/seed{e['seed']}/trajectory.jsonl")
                if hashlib.sha256(raw).hexdigest() != e['trajectory_sha256']:
                    raise ValueError('Strategy trajectory changed')
                metric = score_episode([json.loads(line) for line in raw.splitlines()], spec)
                if any(e[k] != value for k, value in metric.items()):
                    raise ValueError('Strategy score differs')
                measured.append({'case_id': e['case_id'], **metric})
                checked += 1
            if aggregate(measured) != variant['aggregate']:
                raise ValueError('Strategy aggregate differs')
            for case, value in variant['by_case'].items():
                if aggregate([e for e in measured if e['case_id'] == case]) != value:
                    raise ValueError('Case aggregate differs')
    gate = stability_gate(report['variants']['full']['episodes'], spec)
    if gate != json.loads((directory / 'stability.json').read_text()):
        raise ValueError('Stability gate differs')
    if checked != index['episodes'] or checked != 84:
        raise ValueError('Ablation episode count differs')
    return {'verified': True, 'episodes_rescored': checked, 'stability_passed': gate['passed'],
            'model_calls': 0, 'new_simulation_trials': 0}
