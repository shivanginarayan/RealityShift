"""Run the frozen development suite against a validated skill snapshot."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from control.skill_schema import load_skill, skill_text
from evaluation.metrics import aggregate, score_episode
from simulation.nominal import GOAL_TOLERANCE, HORIZON, run_episode

ROOT = Path(__file__).parents[1]


def source_hash(path):
    # Canonicalize line endings so Git's Windows checkout conversion is harmless.
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_frozen(root=ROOT):
    lock = json.loads((root / "evaluation/frozen.json").read_text())
    for name, expected in lock["sha256"].items():
        if source_hash(root / name) != expected:
            raise RuntimeError(f"Frozen benchmark changed: {name}. Use a new benchmark version.")
    spec = json.loads((root / "evaluation/spec.json").read_text())
    if spec["horizon"] != HORIZON or spec["goal_tolerance_xy_m"] != GOAL_TOLERANCE:
        raise RuntimeError("Runner configuration differs from frozen specification")
    return spec, lock


def evaluate(skill_path, output):
    spec, lock = verify_frozen()
    skill = load_skill(skill_path)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "skill.yaml"
    snapshot.write_text(skill_text(skill), encoding="utf-8")
    skill_hash = source_hash(snapshot)
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(),
                "skill_sha256": skill_hash, "benchmark": lock, "spec": spec}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    metrics = []
    for scenario in spec["development_scenarios"]:
        for seed in spec["development_seeds"]:
            verify_frozen()
            if source_hash(snapshot) != skill_hash:
                raise RuntimeError("Skill snapshot was modified during evaluation")
            directory = output / scenario / f"seed{seed}"
            run_episode(seed, directory, scenario, snapshot)
            records = [json.loads(line) for line in (directory / "trajectory.jsonl").read_text().splitlines()]
            result = score_episode(records, spec)
            metrics.append({"scenario": scenario, "seed": seed, **result})
        print(f"Completed {scenario}", flush=True)
    verify_frozen()
    report = {"benchmark_version": spec["version"], "spec_sha256": source_hash(ROOT / "evaluation/spec.json"),
              "skill_sha256": skill_hash, "aggregate": aggregate(metrics), "episodes": metrics}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", type=Path, default=ROOT / "skills/initial.yaml")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "experiments/benchmark" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report = evaluate(args.skill, output)
    print(json.dumps(report["aggregate"], indent=2))
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
