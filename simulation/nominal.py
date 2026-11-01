"""Run the developer's nominal controller and preserve measured trajectories."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import gymnasium as gym
import numpy as np

from control.controller import PushingController
from simulation.environment import ShiftedPusher
from control.skill_schema import load_skill, skill_text


# Development acceptance criteria, set before the ten-seed verification.
# XY distance is used because object and goal have different fixed Z heights.
HORIZON = 300
GOAL_TOLERANCE = 0.05


def run_episode(seed: int, output: Path, scenario_id="nominal", skill_path=None) -> dict:
    skill = load_skill(skill_path or Path(__file__).parents[1] / "skills/initial.yaml")
    output.mkdir(parents=True, exist_ok=True)
    env = ShiftedPusher(scenario_id, horizon=HORIZON)
    # Reference kinematics comes from an independent nominal model, so the
    # controller never receives the shifted simulator's mass or delay settings.
    reference_env = gym.make("Pusher-v5")
    try:
        obs, _ = env.reset(seed=seed)
        controller = PushingController(reference_env.unwrapped.model, skill)
        initial = float(np.linalg.norm(obs[17:19] - obs[20:22]))
        total_reward = 0.0
        max_action = 0.0
        errors = []
        trajectory = output / "trajectory.jsonl"
        with trajectory.open("w", encoding="utf-8") as stream:
            for step in range(1, HORIZON + 1):
                action = controller.action(obs)
                if not np.isfinite(action).all() or not env.action_space.contains(action.astype(np.float32)):
                    raise RuntimeError("Controller returned an invalid action")
                before = obs.copy()
                obs, reward, terminated, truncated, _ = env.step(action)
                if not np.isfinite(obs).all() or not np.isfinite(reward):
                    raise RuntimeError("Non-finite simulator output")
                error = float(np.linalg.norm(obs[17:19] - obs[20:22]))
                errors.append(error)
                total_reward += float(reward)
                max_action = max(max_action, float(np.max(np.abs(action))))
                stream.write(json.dumps({
                    "step": step, "time_seconds": float(env.unwrapped.data.time),
                    "phase": controller.phase, "observation_before": before.tolist(),
                    "action": action.tolist(), "observation_after": obs.tolist(),
                    "applied_action": env.last_applied_action.tolist(),
                    "reward": float(reward), "object_goal_xy_distance": error,
                    "terminated": bool(terminated), "truncated": bool(truncated),
                }, allow_nan=False) + "\n")
                if terminated or truncated:
                    break
        # Require the object to remain within tolerance for the final half second.
        success = len(errors) >= 10 and max(errors[-10:]) <= GOAL_TOLERANCE
        summary = {
            "environment": "Pusher-v5", "scenario": scenario_id,
            "developer_physics_manifest": env.developer_manifest(),
            "controller": "developer_ik_reference_v1", "seed": seed,
            "skill_version": skill.version,
            "skill_sha256": hashlib.sha256(skill_text(skill).encode()).hexdigest(),
            "horizon": HORIZON, "steps": step,
            "goal_tolerance_xy_m": GOAL_TOLERANCE, "settle_steps": 10,
            "success": success, "initial_error_xy_m": initial,
            "final_error_xy_m": errors[-1], "final_settle_max_error_xy_m": max(errors[-10:]),
            "total_reward": total_reward, "max_abs_action": max_action,
            "final_phase": controller.phase,
            "trajectory_sha256": hashlib.sha256(trajectory.read_bytes()).hexdigest(),
            "controller_sha256": hashlib.sha256(Path(__file__).parents[1].joinpath("control/controller.py").read_bytes()).hexdigest(),
            "versions": {p: importlib.metadata.version(p) for p in ("gymnasium", "mujoco", "numpy", "scipy")},
            "note": "Fixed-controller development result; no agent adaptation. Physics manifest is developer-only.",
        }
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        return summary
    finally:
        env.close()
        reference_env.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42])
    parser.add_argument("--output", type=Path, default=Path("experiments/nominal"))
    args = parser.parse_args()
    results = [run_episode(seed, args.output / f"seed{seed}") for seed in args.seeds]
    report = {"episodes": len(results), "successes": sum(r["success"] for r in results),
              "success_rate": sum(r["success"] for r in results) / len(results), "results": results}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    for r in results:
        print(f"seed={r['seed']} success={r['success']} final_error={r['final_error_xy_m']:.4f} m")


if __name__ == "__main__":
    main()
