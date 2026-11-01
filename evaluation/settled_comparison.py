"""Increment 2 developer ablation; existing development cases, never held-out."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import gymnasium as gym
import numpy as np

from agent.recovery_diagnostics import summarize_observations
from control.settled_recovery import ConfirmedRecoveryController, SettledRecoveryController
from control.skill_schema import load_skill
from evaluation.benchmark import ROOT, source_hash
from evaluation.heldout import verify_protocol
from evaluation.metrics import aggregate, score_episode
from evaluation.recovery_comparison import SCENARIOS, SEEDS, protected_hashes
from evaluation.verify_recovery import verify as verify_increment1
from simulation.environment import ShiftedPusher


SOURCES = ['control/recovery.py', 'control/settled_recovery.py',
           'agent/recovery_diagnostics.py', 'evaluation/settled_comparison.py']


def run_episode(factory, seed, scenario, directory, spec):
    directory.mkdir(parents=True, exist_ok=False)
    env = ShiftedPusher(scenario, horizon=spec['horizon'])
    nominal = gym.make('Pusher-v5')
    try:
        obs, _ = env.reset(seed=seed)
        controller = factory(nominal.unwrapped.model, load_skill(ROOT / 'skills/initial.yaml'))
        rows = []
        for step in range(1, spec['horizon'] + 1):
            before = obs.copy()
            action = controller.action(obs)
            if not np.isfinite(action).all() or not env.action_space.contains(action.astype(np.float32)):
                raise RuntimeError('Invalid action')
            obs, reward, terminated, truncated, _ = env.step(action)
            if not np.isfinite(obs).all() or not np.isfinite(reward):
                raise RuntimeError('Invalid simulator observation')
            rows.append({'step': step, 'time_seconds': float(env.unwrapped.data.time),
                         'phase': controller.phase, 'observation_before': before.tolist(),
                         'observation_after': obs.tolist(), 'action': action.tolist(),
                         'applied_action': env.last_applied_action.tolist(),
                         'terminated': bool(terminated), 'truncated': bool(truncated)})
            if terminated or truncated:
                break
        path = directory / 'trajectory.jsonl'
        path.write_text(''.join(json.dumps(row, allow_nan=False) + '\n' for row in rows), encoding='utf-8')
        diagnostic = summarize_observations([r['observation_after'] for r in rows],
                                           [r['phase'] for r in rows], controller.diagnostics())
        return {'scenario': scenario, 'seed': seed, **score_episode(rows, spec),
                'diagnostics': diagnostic, 'policy': controller.diagnostics(),
                'trajectory_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    finally:
        env.close()
        nominal.close()


def compare(output):
    spec, _, _, _ = verify_protocol()
    verify_increment1()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    protected = protected_hashes()
    sources = {name: source_hash(ROOT / name) for name in SOURCES}
    baseline_path = ROOT / 'docs/evidence/recovery-v2/final/report.json'
    baselines = json.loads(baseline_path.read_text())['controllers']
    factories = {'confirmed_recovery': ConfirmedRecoveryController,
                 'settled_recovery': SettledRecoveryController}
    nominal = gym.make('Pusher-v5')
    try:
        policies = {name: factory(nominal.unwrapped.model).diagnostics() for name, factory in factories.items()}
    finally:
        nominal.close()
    manifest = {'experiment': 'developer_recovery_increment2_first', 'authorship': 'developer',
                'created_utc': datetime.now(timezone.utc).isoformat(), 'scoring': spec,
                'seeds': SEEDS, 'scenarios': SCENARIOS, 'policies': policies,
                'source_sha256': sources, 'protected_sha256_before': protected,
                'baseline_report_sha256': hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
                'note': 'Original v1 and increment 1 baselines reused from verified raw evidence. '
                        'Two new strategies, 30 new development episodes. No model calls, held-out access, gain search or promotion.'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    results = {name: [] for name in factories}
    for scenario in SCENARIOS:
        for seed in SEEDS:
            for name, factory in factories.items():
                results[name].append(run_episode(factory, seed, scenario, output / name / scenario / f'seed{seed}', spec))
            print(f'Completed {scenario} seed={seed}', flush=True)
    verify_protocol()
    if protected != protected_hashes() or sources != {name: source_hash(ROOT / name) for name in SOURCES}:
        raise RuntimeError('Sources or protected artifacts changed during comparison')
    reports = {name: {'aggregate': aggregate(rows),
               'by_scenario': {s: aggregate([r for r in rows if r['scenario'] == s]) for s in SCENARIOS},
               'episodes': rows} for name, rows in results.items()}
    report = {'experiment': manifest['experiment'], 'authorship': 'developer',
              'protected_artifacts_unchanged': True, 'controllers': {**baselines, **reports}}
    (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({k: v['aggregate'] for k, v in report['controllers'].items()}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    compare(parser.parse_args().output)
