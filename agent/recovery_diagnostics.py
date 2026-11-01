"""Compact v2 diagnostic formatter. Not registered with the v1 MCP bridge.

Only observations and public controller phases enter this API. Never pass full
runner rows or developer physics manifests into a future agent response.
"""
from collections import Counter

import numpy as np

from control.recovery import FailureDetector, checked_observation


def summarize_observations(observations, phases, recovery=None):
    detector = FailureDetector()
    counts = Counter()
    samples = []
    errors, gaps = [], []
    last_reason = None
    previous_phase = None
    for step, (observation, phase) in enumerate(zip(observations, phases, strict=True), 1):
        obs = checked_observation(observation)
        errors.append(float(np.linalg.norm(obs[17:19] - obs[20:22])))
        gaps.append(float(np.linalg.norm(obs[14:17] - obs[17:20])))
        if phase not in ("push", "hold") or previous_phase not in ("push", "hold"):
            detector.reset()
            last_reason = None
        reason = detector.update(obs) if phase in ("push", "hold") else None
        if reason and reason != last_reason:
            counts[reason] += 1
            if len(samples) < 8:
                samples.append({"step": step, "hypothesis": reason,
                                "goal_error_xy_m": round(errors[-1], 5),
                                "tip_object_gap_m": round(gaps[-1], 5)})
        last_reason = reason
        previous_phase = phase
    if not errors:
        raise ValueError("Diagnostics require observations")
    result = {"schema": "recovery_diagnostics_v2", "steps": len(errors),
              "initial_error_xy_m": round(errors[0], 5),
              "best_error_xy_m": round(min(errors), 5),
              "final_error_xy_m": round(errors[-1], 5),
              "max_tip_object_gap_m": round(max(gaps), 5),
              "failure_hypotheses": dict(counts), "examples": samples,
              "caveat": "Behavioral hypotheses only; separation does not prove physical contact loss."}
    if recovery is not None:
        # Do not forward arbitrary caller fields/configuration/hidden metadata.
        result["recovery"] = {k: recovery[k] for k in
                              ("phase", "retries_used", "retry_limit", "event_counts", "events")}
    return result
