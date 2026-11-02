"""Developer-only post-v2 comparison. Does not change or spend frozen agent runs."""
import argparse
from datetime import datetime, timezone
from functools import partial
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import zipfile

from control.progress_recovery import ProgressRecoveryController
from control.strategy_schema import StrategySkill
from evaluation.benchmark import ROOT, source_hash
from evaluation.metrics import aggregate, score_episode
from evaluation.recovery_comparison import protected_hashes
from evaluation.v2 import benchmark


BASELINE = 'docs/evidence/strategy-v2/reachable-contact-geometry/report.json'
SOURCES = benchmark.SOURCES + ['evaluation/v2/frozen.json', 'control/progress_recovery.py',
                               'evaluation/progress_comparison.py', BASELINE]
VARIANTS = {'baseline': None, 'full': (True, True), 'without_tracking_memory': (False, True),
            'without_braking': (True, False)}


def acceptance(results):
    before, after = results['baseline'], results['full']
    successes = {(e['case_id'], e['seed']) for e in before if e['success']}
    checks = {'all_eligible': all(e['eligible'] for e in after),
              'every_baseline_success_preserved': all(e['success'] for e in after
                  if (e['case_id'], e['seed']) in successes),
              'more_successes': sum(e['success'] for e in after) > len(successes)}
    for case in ('case_d', 'case_e', 'case_f'):
        def recovered(rows):
            return sum(e['success'] and any(v['step'] >= 90 for v in e['strategy_events'])
                       for e in rows if e['case_id'] == case)
        checks[case + '_recovery_nonregression'] = recovered(after) >= recovered(before)
    return {'accepted': all(checks.values()), 'checks': checks,
            'note': 'Development only. No unseen evaluation, model calls, promotion, budget reset or changes to frozen v2.'}


def compare(output):
    benchmark.verify_v2()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    protected = protected_hashes()
    sources = {name: source_hash(ROOT / name) for name in SOURCES}
    spec = benchmark.read_spec()
    manifest = {'authorship': 'developer', 'created_utc': datetime.now(timezone.utc).isoformat(),
                'spec': spec, 'source_sha256': sources, 'protected_sha256_before': protected,
                'variants': VARIANTS,
                'acceptance': 'All baseline successes preserved, more successes, no loss of successful explicit probe recoveries.',
                'runner': 'Frozen v2 episode function, with an explicit in-process controller substitution for developer variants only. Frozen source/agent endpoint unchanged.'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    baseline = {(e['case_id'], e['seed']): e for e in json.loads((ROOT / BASELINE).read_text())['variants']['full']['episodes']}
    results = {name: [] for name in VARIANTS}
    original = benchmark.StrategyController
    for case, data in spec['cases'].items():
        for seed in data['seeds']:
            for name, flags in VARIANTS.items():
                controller = original if flags is None else partial(ProgressRecoveryController,
                    tracking_memory=flags[0], braking=flags[1])
                with patch.object(benchmark, 'StrategyController', controller):
                    episode = benchmark.run_episode(StrategySkill(), case, seed,
                        output / name / case / f'seed{seed}', spec)
                results[name].append(episode)
                if name == 'baseline':
                    for field in ('success', 'score', 'final_error_xy_m', 'mean_squared_torque'):
                        if episode[field] != baseline[case, seed][field]:
                            raise ValueError('Frozen baseline did not reproduce; investigate before interpreting candidate')
            print(f'Completed {case} seed={seed}', flush=True)
    benchmark.verify_v2()
    if protected != protected_hashes() or sources != {p: source_hash(ROOT / p) for p in sources}:
        raise ValueError('Protected artifacts or measured source changed during comparison')
    report = {'authorship': 'developer', 'protected_artifacts_unchanged': True,
              'variants': {name: {'aggregate': aggregate(rows),
                  'by_case': {case: aggregate([e for e in rows if e['case_id'] == case]) for case in spec['cases']},
                  'episodes': rows} for name, rows in results.items()}, 'acceptance': acceptance(results)}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({n: d['aggregate'] for n, d in report['variants'].items()}, indent=2))
    print(json.dumps(report['acceptance'], indent=2))
    return report


def package(origin, destination):
    origin, destination = Path(origin), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name in ('manifest.json', 'report.json'):
        (destination / name).write_bytes((origin / name).read_bytes())
    manifest = json.loads((origin / 'manifest.json').read_text())
    with zipfile.ZipFile(destination / 'trajectories.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        trajectories = sorted(origin.glob('*/*/seed*/trajectory.jsonl'))
        if len(trajectories) != 84:
            raise ValueError('All 84 developer outcomes must be retained')
        for path in trajectories:
            bundle.write(path, path.relative_to(origin).as_posix())
        for name, digest in manifest['source_sha256'].items():
            if source_hash(ROOT / name) != digest:
                raise ValueError('Measured source changed before packaging')
            bundle.write(ROOT / name, 'source/' + name)
    index = {'episodes': 84, 'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             if p.suffix == '.zip' else source_hash(p) for p in destination.iterdir() if p.is_file()}}
    (destination / 'archive.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    return verify(destination)


def verify(directory):
    directory = Path(directory)
    index = json.loads((directory / 'archive.json').read_text())
    for name, digest in index['sha256'].items():
        actual = hashlib.sha256((directory / name).read_bytes()).hexdigest() if name.endswith('.zip') else source_hash(directory / name)
        if actual != digest:
            raise ValueError('Progress evidence changed')
    report = json.loads((directory / 'report.json').read_text())
    manifest = json.loads((directory / 'manifest.json').read_text())
    spec = manifest['spec']
    if set(report['variants']) != set(VARIANTS) or not report['protected_artifacts_unchanged']:
        raise ValueError('Incomplete comparison')
    expected = {(c, s) for c, d in spec['cases'].items() for s in d['seeds']}
    count = 0
    with zipfile.ZipFile(directory / 'trajectories.zip') as bundle:
        for name, digest in manifest['source_sha256'].items():
            raw = bundle.read('source/' + name).decode('utf-8-sig').replace('\r\n', '\n')
            if hashlib.sha256(raw.encode()).hexdigest() != digest:
                raise ValueError('Measured source snapshot differs')
        for name, data in report['variants'].items():
            if len(data['episodes']) != 21 or {(e['case_id'], e['seed']) for e in data['episodes']} != expected:
                raise ValueError('Missing or duplicate episode')
            metrics = []
            for e in data['episodes']:
                raw = bundle.read(f"{name}/{e['case_id']}/seed{e['seed']}/trajectory.jsonl")
                if hashlib.sha256(raw).hexdigest() != e['trajectory_sha256']:
                    raise ValueError('Trajectory changed')
                scored = score_episode([json.loads(line) for line in raw.splitlines()], spec)
                if any(e[k] != v for k, v in scored.items()):
                    raise ValueError('Measured episode differs')
                metrics.append(scored)
                count += 1
            if aggregate(metrics) != data['aggregate']:
                raise ValueError('Measured aggregate differs')
    if acceptance({n: d['episodes'] for n, d in report['variants'].items()}) != report['acceptance']:
        raise ValueError('Acceptance checks differ')
    return {'verified': True, 'episodes_rescored': count, 'accepted': report['acceptance']['accepted'],
            'model_calls': 0, 'new_simulation_trials': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        print(verify(args.verify))
    else:
        compare(args.output)
