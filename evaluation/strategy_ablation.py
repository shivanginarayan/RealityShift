"""Predeclared developer ablations and stability gate for recovery benchmark v2."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from control.strategy_schema import StrategySkill, strategy_text
from evaluation.benchmark import ROOT, source_hash
from evaluation.heldout import verify_protocol
from evaluation.metrics import aggregate
from evaluation.recovery_comparison import protected_hashes
from evaluation.v2.benchmark import SOURCES, read_spec, run_episode


def stability_gate(episodes, spec):
    rules = spec['developer_stability_gate']
    groups = {case: [e for e in episodes if e['case_id'] == case] for case in spec['cases']}
    checks = {'all_eligible': all(e['eligible'] for e in episodes) and len(episodes) == 21,
              'nominal_5_of_5': sum(e['success'] for e in groups['case_a']) == rules['nominal_successes'],
              'mass_at_least_2_of_5': sum(e['success'] for e in groups['case_b']) >= rules['mass_successes_at_least'],
              'delay_at_least_3_of_5': sum(e['success'] for e in groups['case_c']) >= rules['delay_successes_at_least']}
    for case in ('case_d', 'case_e', 'case_f'):
        checks[f'{case}_successful_post_interruption_retry'] = sum(
            e['success'] and any(event['step'] >= spec['probe_step'] for event in e['strategy_events'])
            for e in groups[case]) >= rules['probe_successes_with_retry_at_least_each']
    return {'passed': all(checks.values()), 'checks': checks,
            'note': 'Developer stability only, not unseen generalization. No model run unless every check passes.'}


def compare(output):
    verify_protocol()
    spec = read_spec()
    full = StrategySkill()
    variants = {'full': full,
                'without_stabilization': replace(full, approach='direct', contact='reapproach'),
                'without_repush': replace(full, stall='reapproach'),
                'without_correction': replace(full, overshoot='reapproach')}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    protected = protected_hashes()
    sources = {p: source_hash(ROOT / p) for p in SOURCES + ['evaluation/strategy_ablation.py']}
    manifest = {'created_utc': datetime.now(timezone.utc).isoformat(), 'authorship': 'developer',
                'experiment': 'distinct_recovery_strategies_first_ablation', 'spec': spec,
                'variants': {k: strategy_text(v) for k, v in variants.items()},
                'source_sha256': sources, 'protected_sha256_before': protected,
                'note': 'All 84 outcomes retained. Scripted probe interventions are explicit development tests, not unseen physics.'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    results = {k: [] for k in variants}
    for case_id, case in spec['cases'].items():
        for seed in case['seeds']:
            for label, strategy in variants.items():
                result = run_episode(strategy, case_id, seed, output / label / case_id / f'seed{seed}', spec)
                results[label].append(result)
            print(f'Completed {case_id} seed={seed}', flush=True)
    verify_protocol()
    if protected != protected_hashes() or sources != {p: source_hash(ROOT / p) for p in sources}:
        raise RuntimeError('Original evidence or experiment sources changed during comparison')
    report = {'authorship': 'developer', 'experiment': manifest['experiment'], 'protected_artifacts_unchanged': True,
              'variants': {label: {'aggregate': aggregate(rows),
                  'by_case': {case: aggregate([e for e in rows if e['case_id'] == case]) for case in spec['cases']},
                  'episodes': rows} for label, rows in results.items()}}
    gate = stability_gate(results['full'], spec)
    for name, obj in (('report.json', report), ('stability.json', gate)):
        (output / name).write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({label: data['aggregate'] for label, data in report['variants'].items()}, indent=2))
    print(json.dumps(gate, indent=2))
    return report, gate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    compare(parser.parse_args().output)
