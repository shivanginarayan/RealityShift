"""Compact v3 behavior evidence; input is an explicit observation projection."""
import numpy as np
from agent.strategy_diagnostics import diagnose


def compact(rows):
    result = diagnose(rows)
    segments = result.pop('segments')
    worst = sorted(segments, key=lambda s: s['tip_target_median_m'] or 0, reverse=True)[:6]
    result['segments'] = sorted(worst, key=lambda s: s['start_step'])
    obs = np.asarray([r['observation'] for r in rows])
    result['early_joint_response_rms'] = round(float(np.sqrt(np.mean((obs[min(2, len(obs)-1), 7:14] - obs[0, 7:14]) ** 2))), 5)
    result['max_effective_joint_tracking_error_rms'] = round(max(r.get('joint_error', 0.) for r in rows), 5)
    result['brake_samples'] = sum(bool(r.get('braking', False)) for r in rows)
    result['max_tracking_memory_m'] = round(max(r.get('tracking_memory', 0.) for r in rows), 5)
    result['caveat'] = ('Behavioral hypotheses, not identified dynamics. Early response does not measure latency; '
                        'marker proximity does not measure contact forces. Target is the effective nominal reference.')
    return result
