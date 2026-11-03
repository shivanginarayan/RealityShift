"""Independent three-split actuator-delay protocol; no changes to v1/v2."""
import hashlib
import json
from pathlib import Path
import platform
import importlib.metadata

import gymnasium as gym
import mujoco
import numpy as np

from agent.adaptation_diagnostics import compact
from control.adaptation_schema import make_controller, text
from evaluation.benchmark import ROOT, source_hash
from evaluation.metrics import aggregate, score_episode
from evaluation.v2.benchmark import verify_v2, SOURCES as V2_SOURCES
from simulation.delay_shift import DelayedPusher


DIRECTORY = ROOT / 'evaluation/v3'
CORE = list(dict.fromkeys(V2_SOURCES + ['control/controller.py', 'control/progress_recovery.py',
    'control/response_recovery.py',
    'control/adaptation_schema.py', 'simulation/delay_shift.py', 'agent/adaptation_diagnostics.py',
    'evaluation/v3/spec.json', 'evaluation/v3/benchmark.py', 'evaluation/metrics.py',
    'strategies/v3/initial.yaml', 'strategies/v3/developer.yaml']))
AGENT_SOURCES = ['agent/adaptation_bridge.py', 'agent/adaptation_server.py', 'agent/adaptation_instructions.md',
    'agent/configure_adaptation_trueforge.py', 'agent/run_adaptation_v3.py',
    'evaluation/v3/protocol.py', 'evaluation/v3/final_evaluation.py', 'evaluation/v3/evidence.py']


def spec():
    return json.loads((DIRECTORY / 'spec.json').read_text())


def verify():
    verify_v2()
    path = DIRECTORY / 'frozen.json'
    if not path.is_file():
        raise ValueError('V3 not frozen: complete the developer gate first')
    lock = json.loads(path.read_text())
    for name, digest in lock['source_sha256'].items():
        if source_hash(ROOT / name) != digest:
            raise ValueError(f'V3 frozen source changed: {name}')
    return spec(), lock


def run_episode(skill, condition, output):
    settings = spec()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    env = DelayedPusher(condition['delay_steps'], condition['onset_step'], settings['horizon'])
    nominal = gym.make('Pusher-v5')
    data = mujoco.MjData(nominal.unwrapped.model)
    rows, public = [], []
    try:
        obs, _ = env.reset(seed=condition['seed'])
        controller = make_controller(nominal.unwrapped.model, skill)
        for step in range(1, settings['horizon'] + 1):
            before = obs.copy()
            action = controller.action(before)
            if not np.isfinite(action).all() or np.max(np.abs(action)) > settings['max_abs_torque']:
                raise ValueError('Controller violated action bounds')
            braking = bool(getattr(controller, 'braking_active', False))
            reference = (controller.braking_joints if braking else controller.reference).copy()
            data.qpos[:7] = reference
            mujoco.mj_kinematics(nominal.unwrapped.model, data)
            effective_target = data.xpos[controller.tip_id].copy()
            joint_error = float(np.sqrt(np.mean((reference - before[:7]) ** 2)))
            stage = getattr(controller, 'command_stage', controller.phase)
            debt = float(getattr(controller, 'tracking_debt', 0.))
            obs, _, terminated, truncated, _ = env.step(action)
            rows.append({'step': step, 'time_seconds': float(env.unwrapped.data.time),
                'observation_before': before.tolist(), 'observation_after': obs.tolist(),
                'action': action.tolist(), 'applied_action': env.last_applied_action.tolist(),
                'phase': controller.phase, 'command_stage': stage, 'effective_joint_reference': reference.tolist(),
                'effective_tip_reference': effective_target.tolist(), 'joint_tracking_error_rms': joint_error,
                'braking': braking, 'tracking_memory_m': debt,
                'retries_used': int(getattr(controller, 'retries', 0)),
                'terminated': bool(terminated), 'truncated': bool(truncated)})
            public.append({'observation': before.tolist(), 'issued_action': action.tolist(),
                           'stage': stage, 'target': effective_target.tolist(), 'joint_error': joint_error,
                           'braking': braking, 'tracking_memory': debt})
            if terminated or truncated:
                break
        raw = ''.join(json.dumps(row, allow_nan=False) + '\n' for row in rows).encode()
        (output / 'trajectory.jsonl').write_bytes(raw)
        policy = controller.diagnostics() if hasattr(controller, 'diagnostics') else {}
        result = {'condition_id': condition['id'], **score_episode(rows, settings),
                  'diagnostics': compact(public), 'retries_used': int(getattr(controller, 'retries', 0)),
                  'strategy_events': policy.get('strategy_events', []), 'event_counts': policy.get('event_counts', {}),
                  'brake_activations': int(policy.get('event_counts', {}).get('observed_closing_brake', 0)),
                  'trajectory_sha256': hashlib.sha256(raw).hexdigest()}
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        return result
    finally:
        env.close()
        nominal.close()


def evaluate(skill, split, output, *, heldout_authorized=False):
    settings, lock = verify()
    if split not in ('development', 'validation', 'heldout') or split == 'heldout' and not heldout_authorized:
        raise ValueError('Final heldout is available only through its one-shot reservation')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    yaml = text(skill)
    (output / 'policy.yaml').write_text(yaml, encoding='utf-8')
    episodes = []
    for condition in settings['splits'][split]:
        verify()
        episodes.append(run_episode(skill, condition, output / condition['id']))
        print(f"{output.name}: {condition['id']} {'success' if episodes[-1]['success'] else 'failure'}", flush=True)
    verify()
    report = {'benchmark_version': 3, 'split': split, 'policy_sha256': hashlib.sha256(yaml.encode()).hexdigest(),
              'frozen_sha256': source_hash(DIRECTORY / 'frozen.json'),
              'aggregate': aggregate(episodes), 'episodes': episodes,
              'versions': {p: importlib.metadata.version(p) for p in ('gymnasium', 'mujoco', 'numpy', 'scipy')},
              'python': platform.python_version()}
    (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return report


def public_episode(episode, diagnostics=False):
    fields = ['condition_id', 'eligible', 'success', 'score', 'final_error_xy_m', 'mean_squared_torque',
              'settled_time_fraction', 'retries_used', 'brake_activations']
    if diagnostics:
        fields += ['diagnostics', 'strategy_events', 'event_counts']
    return {k: episode[k] for k in fields}


def promotion(before, after):
    from evaluation.metrics import can_promote
    old = {e['condition_id']: e for e in before['episodes']}
    new = {e['condition_id']: e for e in after['episodes']}
    same = set(old) == set(new) and len(old) == len(before['episodes']) == len(after['episodes'])
    preserved = same and all(new[k]['success'] for k, e in old.items() if e['success'])
    return bool(preserved and can_promote(before['aggregate'], after['aggregate']))
