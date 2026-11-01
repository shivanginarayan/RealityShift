"""Reconstruct recovery targets from archived observations; no simulated trials."""
import argparse
import json
from pathlib import Path
import zipfile

import gymnasium as gym

from agent.strategy_diagnostics import diagnose
from control.recovery import RecoveryController
from control.settled_recovery import SettledRecoveryController
from evaluation.benchmark import ROOT
from evaluation.verify_recovery import verify as verify_increment1
from evaluation.verify_settled import verify as verify_increment2


def analyze():
    verify_increment1()
    verify_increment2()
    sources = [('increment1', ROOT / 'docs/evidence/recovery-v2/trajectories.zip',
                'final/developer_recovery_v2', RecoveryController),
               ('increment2', ROOT / 'docs/evidence/recovery-increment2/trajectories.zip',
                'settled_recovery', SettledRecoveryController)]
    env = gym.make('Pusher-v5')
    results = []
    try:
        for label, archive, prefix, factory in sources:
            with zipfile.ZipFile(archive) as bundle:
                for name in sorted(n for n in bundle.namelist() if n.startswith(prefix + '/') and n.endswith('trajectory.jsonl')):
                    records = [json.loads(line) for line in bundle.read(name).splitlines()]
                    controller = factory(env.unwrapped.model)
                    public = []
                    for row in records:
                        stage = controller.phase
                        target, _ = controller.target(row['observation_before'])
                        if controller.phase != row['phase']:
                            raise ValueError('Reconstructed phase disagrees with archive')
                        if controller.phase == 'recover_brake' and stage != 'recover_brake':
                            stage = 'recover_brake'  # timeout target is the NEW brake anchor
                        public.append({'observation': row['observation_before'], 'stage': stage,
                                       'target': target.tolist() if target is not None else None,
                                       'issued_action': row['action']})
                    # Final observation is needed for actual final-ten-state settling.
                    public.append({'observation': records[-1]['observation_after'], 'stage': controller.phase,
                                   'target': None, 'issued_action': records[-1]['action']})
                    results.append({'controller': label, 'scenario': name.split('/')[-3],
                                    'seed': int(name.split('/')[-2][4:]), **diagnose(public)})
    finally:
        env.close()
    return {'method': 'Exact phase/target reconstruction from recorded before-observations; no IK or simulator steps.',
            'new_simulation_trials': 0, 'model_calls': 0, 'episodes': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps([e for e in result['episodes'] if e['scenario'] == 'actuator_delay' and e['controller'] == 'increment1'], indent=2))
