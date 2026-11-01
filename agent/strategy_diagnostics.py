"""Observation/target/issued-command diagnostics; no simulator metadata inputs."""
import numpy as np


def reversals(values, deadband):
    values = np.asarray(values)
    total = count = 0
    for column in values.T:
        signs = np.sign(column[np.abs(column) > deadband])
        total += int(np.count_nonzero(signs[1:] != signs[:-1]))
        count += max(0, len(signs) - 1)
    return round(total / max(count, 1), 5)


def diagnose(rows):
    """Rows are an explicit public projection, never full environment records."""
    if not rows:
        raise ValueError('Empty diagnostic history')
    observations = np.asarray([r['observation'] for r in rows], dtype=float)
    actions = np.asarray([r['issued_action'] for r in rows], dtype=float)
    if observations.shape != (len(rows), 23) or actions.shape != (len(rows), 7):
        raise ValueError('Invalid diagnostic shapes')
    if not np.isfinite(observations).all() or not np.isfinite(actions).all():
        raise ValueError('Non-finite diagnostic history')
    errors = np.linalg.norm(observations[:, 17:19] - observations[:, 20:22], axis=1)
    gaps = np.linalg.norm(observations[:, 14:17] - observations[:, 17:20], axis=1)
    segments = []
    start = 0
    for end in range(1, len(rows) + 1):
        if end < len(rows) and rows[end]['stage'] == rows[start]['stage']:
            continue
        chunk = rows[start:end]
        targets = [(i, r['target']) for i, r in enumerate(chunk, start) if r.get('target') is not None]
        distances = [float(np.linalg.norm(observations[i, 14:17] - np.asarray(t))) for i, t in targets]
        ik_errors = [r['nominal_ik_error'] for r in chunk if r.get('nominal_ik_error') is not None]
        segment = {'stage': rows[start]['stage'], 'start_step': start + 1, 'end_step': end,
                   'tip_target_min_m': round(min(distances), 5) if distances else None,
                   'tip_target_median_m': round(float(np.median(distances)), 5) if distances else None,
                   'tip_target_final_m': round(distances[-1], 5) if distances else None,
                   'nominal_ik_error_median_m': round(float(np.median(ik_errors)), 5) if ik_errors else None,
                   'goal_progress_m': round(float(errors[start] - errors[end - 1]), 5),
                   'proximity_fraction': round(float(np.mean(gaps[start:end] <= .065)), 5),
                   'joint_velocity_reversal_fraction': reversals(observations[start:end, 7:14], .1),
                   'issued_torque_reversal_fraction': reversals(actions[start:end], .2),
                   'saturated_torque_fraction': round(float(np.mean(np.abs(actions[start:end]) >= 1.9)), 5)}
        segments.append(segment)
        start = end
    approach = [s for s in segments if s['stage'] in
                ('approach', 'lower', 'recover_lift', 'recover_reapproach', 'recover_lower',
                 'stabilize', 'reposition', 'correct_lower')]
    push_indices = [i for i, r in enumerate(rows) if r['stage'] in ('push', 'repush')]
    acquired = any(gaps[i] <= .065 for i in push_indices)
    failed = max(errors[-10:]) > .05 or len(rows) < 10
    labels = []
    if failed and any(s['nominal_ik_error_median_m'] is not None
                      and s['nominal_ik_error_median_m'] > .04 for s in approach):
        labels.append('approach_ik_objective_failure')
    if failed and any(s['end_step'] - s['start_step'] >= 20
                      and s['tip_target_median_m'] is not None and s['tip_target_median_m'] > .08 for s in approach):
        labels.append('approach_tracking_failure')
    if failed and push_indices and not acquired:
        labels.append('contact_acquisition_failure')
    if failed and acquired:
        labels.append('pushing_or_settling_failure')
    if any(s['end_step'] - s['start_step'] >= 20 and s['joint_velocity_reversal_fraction'] > .08
           and s['saturated_torque_fraction'] > .3 for s in approach):
        labels.append('control_oscillation')
    return {'schema': 'strategy_diagnostics_v2', 'failure_categories': labels,
            'settled': not failed, 'final_error_xy_m': round(float(errors[-1]), 5),
            'best_error_xy_m': round(float(min(errors)), 5),
            'push_observed': bool(push_indices), 'contact_proximity_observed': acquired,
            'segments': segments[:16], 'segments_total': len(segments),
            'caveat': 'Categories may coexist. Proximity is not a contact sensor; oscillation does not identify its cause.'}
