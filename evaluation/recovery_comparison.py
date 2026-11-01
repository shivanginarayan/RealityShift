"""Developer-only paired v2 smoke comparison, NOT benchmark v1 or held-out eval.

Uses the initial v1 numeric gains for both controllers and existing development
seeds 0..4 only. No tools, model calls, skill writes or promotion occur here.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import argparse

import gymnasium as gym
import numpy as np

from agent.recovery_diagnostics import summarize_observations
from control.recovery import RecoveryConfig, RecoveryController
from control.skill_schema import load_skill
from evaluation.benchmark import ROOT, source_hash, verify_frozen
from evaluation.heldout import verify_protocol
from evaluation.metrics import aggregate, score_episode
from simulation.environment import ShiftedPusher
from simulation.nominal import run_episode


SEEDS = [0, 1, 2, 3, 4]
SCENARIOS = ["nominal", "high_mass", "actuator_delay"]
SOURCES = ["control/recovery.py", "agent/recovery_diagnostics.py",
           "evaluation/recovery_comparison.py"]


def protected_hashes():
    """Protect all original evidence/skills, freeze locks and local receipts."""
    paths = set()
    for directory in ("skills", "docs/evidence", "demo/assets"):
        paths.update(p for p in (ROOT / directory).rglob("*") if p.is_file())
    for name in ("evaluation/frozen.json", "evaluation/heldout_frozen.json",
                 "agent/tool_bridge.py", "agent/instructions.md",
                 ".runtime/bridge/state.json", ".runtime/heldout-receipt.json"):
        if (ROOT / name).is_file():
            paths.add(ROOT / name)
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def run_recovery(seed, scenario, directory, spec):
    directory.mkdir(parents=True, exist_ok=False)
    env = ShiftedPusher(scenario, horizon=spec["horizon"])
    reference = gym.make("Pusher-v5")
    try:
        obs, _ = env.reset(seed=seed)
        controller = RecoveryController(reference.unwrapped.model,
                                        load_skill(ROOT / "skills/initial.yaml"))
        records = []
        for step in range(1, spec["horizon"] + 1):
            before = obs.copy()
            action = controller.action(obs)
            if not np.isfinite(action).all() or not env.action_space.contains(action.astype(np.float32)):
                raise RuntimeError("Invalid recovery action")
            obs, reward, terminated, truncated, _ = env.step(action)
            if not np.isfinite(obs).all() or not np.isfinite(reward):
                raise RuntimeError("Invalid simulator output")
            records.append({"step": step, "time_seconds": float(env.unwrapped.data.time),
                            "phase": controller.phase, "observation_before": before.tolist(),
                            "observation_after": obs.tolist(), "action": action.tolist(),
                            "applied_action": env.last_applied_action.tolist(),
                            "terminated": bool(terminated), "truncated": bool(truncated)})
            if terminated or truncated:
                break
        trajectory = directory / "trajectory.jsonl"
        trajectory.write_text("".join(json.dumps(r, allow_nan=False) + "\n" for r in records),
                              encoding="utf-8")
        return records, controller.diagnostics()
    finally:
        env.close()
        reference.close()


def compare(output):
    spec, _ = verify_frozen()
    verify_protocol()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    protected = protected_hashes()
    sources = {name: source_hash(ROOT / name) for name in SOURCES}
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(),
                "experiment": "developer_recovery_v2_increment1", "authorship": "developer",
                "seeds": SEEDS, "scenarios": SCENARIOS, "scoring": spec,
                "recovery_config": asdict(RecoveryConfig()), "source_sha256": sources,
                "protected_sha256_before": protected,
                "versions": {p: importlib.metadata.version(p) for p in ("gymnasium", "mujoco", "numpy", "scipy")},
                "note": "Development comparison only; same initial gains. Not model-driven, held-out or a v1 promotion."}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    results = {"original_v1": [], "developer_recovery_v2": []}
    for scenario in SCENARIOS:
        for seed in SEEDS:
            for label in results:
                verify_protocol()
                directory = output / label / scenario / f"seed{seed}"
                if label == "original_v1":
                    run_episode(seed, directory, scenario, ROOT / "skills/initial.yaml")
                    rows = [json.loads(line) for line in (directory / "trajectory.jsonl").read_text().splitlines()]
                    recovery = None
                else:
                    rows, recovery = run_recovery(seed, scenario, directory, spec)
                diagnostics = summarize_observations([r["observation_after"] for r in rows],
                                                     [r["phase"] for r in rows], recovery)
                results[label].append({"scenario": scenario, "seed": seed,
                                       **score_episode(rows, spec), "diagnostics": diagnostics,
                                       "trajectory_sha256": hashlib.sha256((directory / "trajectory.jsonl").read_bytes()).hexdigest()})
            print(f"Completed paired {scenario} seed={seed}", flush=True)
    verify_protocol()
    if protected != protected_hashes() or sources != {n: source_hash(ROOT / n) for n in SOURCES}:
        raise RuntimeError("Protected artifacts or comparison sources changed during execution")
    report = {"experiment": manifest["experiment"], "authorship": "developer",
              "original_artifacts_unchanged": True, "source_sha256": sources,
              "controllers": {label: {"aggregate": aggregate(rows),
                  "by_scenario": {s: aggregate([r for r in rows if r["scenario"] == s]) for s in SCENARIOS},
                  "episodes": rows} for label, rows in results.items()}}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({label: value["aggregate"] for label, value in report["controllers"].items()}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    compare(parser.parse_args().output)
