"""Draft/locked v2 runner. Physics/probe settings never enter the controller."""
import hashlib
import json
from pathlib import Path

import gymnasium as gym
import mujoco
import numpy as np

from agent.strategy_diagnostics import diagnose
from control.strategies import StrategyController
from control.strategy_schema import load_strategy, strategy_text
from evaluation.benchmark import ROOT, source_hash
from evaluation.heldout import verify_protocol
from evaluation.metrics import aggregate, score_episode


DIRECTORY = ROOT / 'evaluation/v2'
SOURCES = ['evaluation/v2/spec.json', 'evaluation/v2/benchmark.py', 'control/strategies.py',
           'control/strategy_schema.py', 'agent/strategy_diagnostics.py',
           'control/recovery.py', 'control/settled_recovery.py', 'strategies/v2/initial.yaml']


def read_spec():
    return json.loads((DIRECTORY / 'spec.json').read_text())


def verify_v2():
    verify_protocol()
    path = DIRECTORY / 'frozen.json'
    if not path.is_file():
        raise ValueError('V2 is not enabled: developer stability gate has not passed')
    lock = json.loads(path.read_text())
    for name, expected in lock['source_sha256'].items():
        if source_hash(ROOT / name) != expected:
            raise ValueError(f'V2 frozen artifact changed: {name}')
    gate = json.loads((ROOT / lock['gate_path']).read_text())
    if source_hash(ROOT / lock['gate_path']) != lock['gate_sha256'] or gate.get('passed') is not True:
        raise ValueError('Developer gate evidence changed or failed')
    return read_spec(), lock


def run_episode(strategy, case_id, seed, directory, spec=None):
    spec = spec or verify_v2()[0]
    if case_id not in spec['cases'] or type(seed) is not int or seed not in spec['cases'][case_id]['seeds']:
        raise ValueError('Only listed v2 development cases/seeds are allowed')
    case = spec['cases'][case_id]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    env = ShiftedPusher(case['scenario'], horizon=spec['horizon'])
    reference = gym.make('Pusher-v5')
    rows, public = [], []
    intervention = None
    try:
        obs, _ = env.reset(seed=seed)
        controller = StrategyController(reference.unwrapped.model, strategy)
        frozen_object = None
        for step in range(1, spec['horizon'] + 1):
            applied_probe = False
            # Developer-only scripted interventions. They are explicit known
            # development probes, not realistic/unseen physics or agent actions.
            if case['intervention'] and step == spec['probe_step']:
                data, model = env.unwrapped.data, env.unwrapped.model
                if case['intervention'] == 'contact_interrupt':
                    delta = obs[20:22] - obs[17:19]
                    delta /= max(np.linalg.norm(delta), 1e-9)
                    xy = obs[17:19] + spec['contact_interrupt_m'] * np.array([-delta[1], delta[0]])
                elif case['intervention'] == 'goal_crossing':
                    delta = obs[20:22] - obs[17:19]
                    delta /= max(np.linalg.norm(delta), 1e-9)
                    xy = obs[20:22] + spec['goal_crossing_m'] * delta
                else:
                    xy = obs[17:19].copy()
                body_xy = model.body('object').pos[:2]
                data.qpos[8], data.qpos[7] = xy - body_xy
                data.qvel[7:9] = 0
                mujoco.mj_forward(model, data)
                obs = env.unwrapped._get_obs()
                frozen_object = data.qpos[7:9].copy()
                intervention = {'step': step, 'kind': case['intervention'], 'controller_phase': controller.phase}
                applied_probe = True
            if case['intervention'] == 'object_stall' and frozen_object is not None and step < spec['probe_step'] + spec['stall_steps']:
                env.unwrapped.data.qpos[7:9] = frozen_object
                env.unwrapped.data.qvel[7:9] = 0
                mujoco.mj_forward(env.unwrapped.model, env.unwrapped.data)
                obs = env.unwrapped._get_obs()
                applied_probe = True
            before = obs.copy()
            action = controller.action(obs)
            if not np.isfinite(action).all() or not env.action_space.contains(action.astype(np.float32)):
                raise RuntimeError('Invalid strategy action')
            obs, reward, terminated, truncated, _ = env.step(action)
            if not np.isfinite(obs).all() or not np.isfinite(reward):
                raise RuntimeError('Invalid simulator output')
            rows.append({'step': step, 'time_seconds': float(env.unwrapped.data.time),
                         'phase': controller.phase, 'command_stage': controller.command_stage,
                         'command_target': controller.command_target.tolist() if controller.command_target is not None else None,
                         'nominal_ik_error': controller.nominal_ik_error,
                         'joint_reference_error_rms': float(np.sqrt(np.mean((controller.reference - before[:7]) ** 2))),
                         'observation_before': before.tolist(), 'observation_after': obs.tolist(),
                         'action': action.tolist(), 'applied_action': env.last_applied_action.tolist(),
                         'developer_intervention': applied_probe,
                         'terminated': bool(terminated), 'truncated': bool(truncated)})
            public.append({'observation': before.tolist(), 'issued_action': action.tolist(),
                           'stage': controller.command_stage, 'target': rows[-1]['command_target'],
                           'nominal_ik_error': controller.nominal_ik_error})
            if terminated or truncated:
                break
        public.append({'observation': obs.tolist(), 'issued_action': action.tolist(),
                       'stage': controller.phase, 'target': None})
        trajectory = directory / 'trajectory.jsonl'
        trajectory.write_text(''.join(json.dumps(r, allow_nan=False) + '\n' for r in rows), encoding='utf-8')
        diagnostic = diagnose(public)
        policy = controller.diagnostics()
        return {'case_id': case_id, 'seed': seed, **score_episode(rows, spec), 'diagnostics': diagnostic,
                'retries_used': controller.retries, 'strategy_events': policy['strategy_events'],
                'event_counts': policy['event_counts'], 'stabilized_tracking': controller.stable,
                'developer_intervention': intervention,
                'trajectory_sha256': hashlib.sha256(trajectory.read_bytes()).hexdigest()}
    finally:
        env.close()
        reference.close()


# Import here keeps the public diagnostic/controller modules physics-agnostic.
from simulation.environment import ShiftedPusher


def evaluate(strategy_path, output):
    spec, lock = verify_v2()
    strategy = load_strategy(strategy_path)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    text = strategy_text(strategy)
    (output / 'strategy.yaml').write_text(text, encoding='utf-8')
    metrics = []
    for case_id, case in spec['cases'].items():
        for seed in case['seeds']:
            verify_v2()
            metrics.append(run_episode(strategy, case_id, seed, output / case_id / f'seed{seed}', spec))
    verify_v2()
    report = {'benchmark_version': 2, 'strategy_sha256': hashlib.sha256(text.encode()).hexdigest(),
              'lock': lock, 'aggregate': aggregate(metrics), 'episodes': metrics}
    (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return report
