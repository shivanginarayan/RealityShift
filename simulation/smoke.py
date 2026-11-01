"""Record a seeded simulator installation check; this is not a pushing policy."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import gymnasium as gym
import numpy as np


def run_episode(seed: int, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    trajectory = output / "trajectory.jsonl"
    env = gym.make("Pusher-v5")
    total_reward = 0.0
    try:
        observation, _ = env.reset(seed=seed)
        initial_observation = observation.tolist()
        env.action_space.seed(seed)
        with trajectory.open("w", encoding="utf-8") as stream:
            for step in range(1, env.spec.max_episode_steps + 1):
                action = env.action_space.sample()
                before = observation.copy()
                observation, reward, terminated, truncated, info = env.step(action)
                if not np.isfinite(observation).all() or not np.isfinite(reward):
                    raise RuntimeError(f"Non-finite simulator output at step {step}")
                total_reward += float(reward)
                record = {
                    "step": step,
                    "time_seconds": float(env.unwrapped.data.time),
                    "observation_before": before.tolist(),
                    "action": action.tolist(),
                    "observation_after": observation.tolist(),
                    "reward": float(reward),
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                    "reward_terms": {k: float(v) for k, v in info.items()
                                     if k.startswith("reward_")},
                }
                stream.write(json.dumps(record, allow_nan=False) + "\n")
                if terminated or truncated:
                    break
        summary = {
            "environment": "Pusher-v5", "scenario": "nominal",
            "policy": "seeded_random_smoke_only", "seed": seed,
            "steps": step, "total_reward": total_reward,
            "initial_observation": initial_observation,
            "final_observation": observation.tolist(),
            "final_object_goal_distance": float(np.linalg.norm(observation[17:20] - observation[20:23])),
            "observation_shape": list(env.observation_space.shape),
            "action_shape": list(env.action_space.shape),
            "terminated": bool(terminated), "truncated": bool(truncated),
            "python": platform.python_version(),
            "versions": {p: importlib.metadata.version(p) for p in
                         ("gymnasium", "mujoco", "numpy", "scipy", "PyYAML", "pytest")},
            "trajectory_sha256": hashlib.sha256(trajectory.read_bytes()).hexdigest(),
        }
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        return summary
    finally:
        env.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("experiments/smoke/seed42"))
    args = parser.parse_args()
    print(json.dumps(run_episode(args.seed, args.output), indent=2))


if __name__ == "__main__":
    main()
