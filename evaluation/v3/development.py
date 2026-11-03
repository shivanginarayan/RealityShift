"""Pre-validation developer feasibility check; never reads validation/heldout outcomes."""
import json
from pathlib import Path

from control.adaptation_schema import load
from evaluation.benchmark import ROOT, source_hash
from evaluation.recovery_comparison import protected_hashes
from evaluation.v2.benchmark import verify_v2
from evaluation.v3.benchmark import CORE, run_episode, spec
from evaluation.metrics import aggregate


def run(output=None):
    verify_v2()
    output = Path(output) if output else ROOT / '.runtime/adaptation-v3/development'
    output.mkdir(parents=True, exist_ok=False)
    sources = {p: source_hash(ROOT / p) for p in CORE + ['evaluation/v3/development.py']}
    protected = protected_hashes()
    results = {'original': [], 'developer': []}
    for condition in spec()['splits']['development']:
        for label in results:
            skill = load(ROOT / f'strategies/v3/{"initial" if label == "original" else "developer"}.yaml')
            episode = run_episode(skill, condition, output / label / condition['id'])
            results[label].append(episode)
        print(condition['id'], [results[k][-1]['success'] for k in results], flush=True)
    nominal = {c['id'] for c in spec()['splits']['development'] if c['delay_steps'] == 0}
    four_step = {c['id'] for c in spec()['splits']['development'] if c['delay_steps'] == 4 and c['onset_step'] == 0}
    old = {e['condition_id']: e for e in results['original']}
    new = {e['condition_id']: e for e in results['developer']}
    checks = {'all_eligible': all(e['eligible'] for rows in results.values() for e in rows),
              'nominal_nonregression': all(new[k]['success'] for k in nominal if old[k]['success']),
              'unchanged_four_step_delay_conversion': any(not old[k]['success'] and new[k]['success'] for k in four_step)}
    if protected != protected_hashes() or sources != {p: source_hash(ROOT / p) for p in sources}:
        raise ValueError('Protected artifact or measured development source changed')
    report = {'authorship': 'developer', 'source_sha256': sources, 'protected_sha256': protected,
              'variants': {k: {'aggregate': aggregate(v), 'episodes': v} for k, v in results.items()},
              'gate': {'passed': all(checks.values()), 'checks': checks}}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:v['aggregate'] for k,v in report['variants'].items()}, indent=2))
    print(json.dumps(report['gate'], indent=2))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    run(parser.parse_args().output)
