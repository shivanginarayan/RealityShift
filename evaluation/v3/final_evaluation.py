"""One reserved final test, only after all four policies have been frozen."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from control.adaptation_schema import load, text
from evaluation.benchmark import ROOT, source_hash
from evaluation.v3.benchmark import evaluate, verify


def wilson(successes, n):
    z = 1.959963984540054
    p = successes / n
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    return [max(0., center-half), min(1., center+half)]


def summarize(report):
    episodes = report['episodes']
    return {**report['aggregate'], 'success_wilson_95': wilson(sum(e['success'] for e in episodes), len(episodes)),
            'mean_final_error_m': float(np.mean([e['final_error_xy_m'] for e in episodes])),
            'mean_squared_torque': float(np.mean([e['mean_squared_torque'] for e in episodes])),
            'recovery_entries': sum(e['retries_used'] for e in episodes),
            'predictive_brake_activations': sum(e['brake_activations'] for e in episodes),
            'failure_categories': {label: sum(label in e['diagnostics']['failure_categories'] for e in episodes if not e['success'])
                for label in sorted({c for e in episodes if not e['success'] for c in e['diagnostics']['failure_categories']})}}


def paired_intervals(before, after, conditions):
    old = {e['condition_id']: e for e in before['episodes']}
    new = {e['condition_id']: e for e in after['episodes']}
    clusters = sorted({c['seed'] for c in conditions})
    rng = np.random.default_rng(20261102)
    result = {}
    for field in ('success', 'final_error_xy_m', 'mean_squared_torque'):
        means = [np.mean([float(new[c['id']][field])-float(old[c['id']][field])
                         for c in conditions if c['seed'] == seed]) for seed in clusters]
        sampled = np.asarray(means)[rng.integers(0, len(means), size=(5000, len(means)))].mean(axis=1)
        result[field] = {'candidate_minus_original': float(np.mean(means)),
                         'paired_seed_cluster_bootstrap_95': np.quantile(sampled, [.025, .975]).tolist()}
    return {'starting_seed_clusters': len(clusters), 'resamples': 5000,
            'note': 'Few seed clusters; intervals are descriptive and do not establish broad transfer.', 'metrics': result}


def reserve_final(path, policies):
    record = {'status': 'reserved_before_any_final_outcome', 'reserved_utc': datetime.now(timezone.utc).isoformat(),
              'policies': {label: {'yaml': text(policy), 'sha256': hashlib.sha256(text(policy).encode()).hexdigest()}
                           for label, policy in policies.items()}}
    Path(path).open('x', encoding='utf-8').write(json.dumps(record, indent=2) + '\n')
    return record


def finalize():
    settings, _ = verify()
    root = ROOT / '.runtime/adaptation-v3'
    if (root / 'operation.lock').exists():
        raise ValueError('Agent tool operation still running')
    exports = sorted((root / 'agent_runs').glob('*/evidence.json'))
    if not exports or not all(json.loads(p.read_text())['terminal'] for p in exports):
        raise ValueError('Collect all terminal agent turns before finalizing')
    state = json.loads((root / 'state.json').read_text())
    search = json.loads((root / 'conventional/search.json').read_text())
    if search['used_evaluations'] != 6:
        raise ValueError('Finish the predeclared conventional comparison first')
    promoted = state['promoted']
    agent_path = ROOT / 'strategies/v3/initial.yaml' if promoted == 'initial' else root / 'strategies' / f'{promoted}.yaml'
    if promoted != 'initial':
        decisions = [json.loads(line) for line in (root / 'audit.jsonl').read_text().splitlines()]
        if not any(e['operation'] == 'promotion_decision' and e['accepted'] and
                   state['runs'][e['candidate']]['strategy_id'] == promoted for e in decisions):
            raise ValueError('No genuine accepted promotion receipt for the final agent policy')
        matching = [r for r in state['runs'].values() if r['strategy_id'] == promoted]
        canonical = hashlib.sha256(text(load(agent_path)).encode()).hexdigest()
        if not any(json.loads((root / 'evaluations' / run_id / 'report.json').read_text())['policy_sha256'] == canonical
                   and source_hash(root / 'evaluations' / run_id / 'report.json') == receipt['report_sha256']
                   for run_id, receipt in state['runs'].items() if receipt['strategy_id'] == promoted):
            raise ValueError('Final agent policy differs from its actual measured revision')
    policies = {'original': load(ROOT / 'strategies/v3/initial.yaml'),
                'developer': load(ROOT / 'strategies/v3/developer.yaml'),
                'conventional': load(root / f"conventional/run{search['best_index']}/policy.yaml"),
                'trueforge': load(agent_path)}
    operation = root / 'operation.lock'
    with operation.open('x', encoding='utf-8') as stream:
        try:
            stream.write('finalization')
            reserve_final(root / 'finalized.json', policies)
        finally:
            stream.close()
            operation.unlink()
    output = root / 'final'
    output.mkdir(exist_ok=False)
    reports = {label: evaluate(policy, 'heldout', output / label, heldout_authorized=True)
               for label, policy in policies.items()}
    summary = {'benchmark_version': 3, 'first_and_only_final_results': True,
               'policies_frozen_before_outcomes': json.loads((root / 'finalized.json').read_text()),
               'results': {label: summarize(report) for label, report in reports.items()},
               'paired_vs_original': {label: paired_intervals(reports['original'], report, settings['splits']['heldout'])
                                      for label, report in reports.items() if label != 'original'},
               'conditions': len(settings['splits']['heldout']),
               'uncertainty_caveat': 'Wilson bounds treat episodes descriptively; paired intervals resample five starting-seed clusters.',
               'scope': 'Simulation, unseen starting seeds and interpolated unseen delay/onset settings. No hardware or clinical validation.'}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    (root / 'final-completion.json').open('x', encoding='utf-8').write(json.dumps({
        'status': 'completed', 'summary_sha256': source_hash(output / 'summary.json')}, indent=2) + '\n')
    print(json.dumps(summary['results'], indent=2))
    return summary


if __name__ == '__main__':
    finalize()
