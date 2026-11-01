"""Derive metrics independently from raw observations and commands."""
import math


def score_episode(records, spec):
    violations = []
    if len(records) != spec["horizon"]:
        return {"eligible": False, "violations": ["incomplete_episode"], "score": 0.0,
                "success": False}
    errors, efforts = [], []
    for step, row in enumerate(records, 1):
        if row["step"] != step or not math.isclose(row["time_seconds"], step * spec["dt_seconds"], abs_tol=1e-8):
            violations.append("invalid_step_or_time")
        obs = row["observation_after"]
        if len(obs) != 23 or not all(type(x) in (int, float) and math.isfinite(x) for x in obs):
            violations.append("invalid_observation")
            continue
        errors.append(math.hypot(obs[17] - obs[20], obs[18] - obs[21]))
        for name in ("action", "applied_action"):
            action = row[name]
            if len(action) != 7 or not all(type(x) in (int, float) and math.isfinite(x)
                                           and abs(x) <= spec["max_abs_torque"] for x in action):
                violations.append("invalid_action")
        efforts.append(sum(x * x for x in row["action"]) / 7)
    if violations:
        return {"eligible": False, "violations": sorted(set(violations)), "score": 0.0,
                "success": False}
    settle = spec["settle_steps"]
    success = max(errors[-settle:]) <= spec["goal_tolerance_xy_m"]
    # Settling time is the start of the final continuously successful suffix.
    last_outside = max((i for i, e in enumerate(errors) if e > spec["goal_tolerance_xy_m"]), default=-1)
    settled_fraction = (last_outside + 1) / len(errors) if success else 1.0
    normalized_error = min(errors[-1] / spec["error_normalization_m"], 1.0)
    weights = spec["weights"]
    score = weights["success"] * success + weights["error"] * (1 - normalized_error) + weights["time"] * (1 - settled_fraction)
    return {"eligible": True, "violations": [], "success": success, "score": score,
            "final_error_xy_m": errors[-1], "settled_time_fraction": settled_fraction,
            "mean_squared_torque": sum(efforts) / len(efforts)}


def aggregate(episodes):
    if not episodes:
        raise ValueError("Empty evaluation suite")
    eligible = all(e["eligible"] for e in episodes)
    successes = sum(e["success"] for e in episodes)
    return {"eligible": eligible, "episodes": len(episodes), "successes": successes,
            "success_rate": successes / len(episodes),
            "score": sum(e["score"] for e in episodes) / len(episodes) if eligible else 0.0,
            "rank": [successes / len(episodes),
                     -sum(e.get("final_error_xy_m", 1e6) for e in episodes) / len(episodes),
                     -sum(e.get("mean_squared_torque", 1e6) for e in episodes) / len(episodes)]}


def can_promote(baseline, candidate):
    return (baseline["eligible"] and candidate["eligible"]
            and candidate["rank"] > baseline["rank"] and candidate["score"] > baseline["score"])
