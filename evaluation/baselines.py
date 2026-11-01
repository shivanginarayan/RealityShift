"""Seeded random search with the same four full evaluations as the agent budget."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import random

from control.skill_schema import LIMITS, load_skill, parse_skill, skill_text
from evaluation.benchmark import ROOT, evaluate, source_hash, verify_frozen
from evaluation.metrics import can_promote

CANDIDATES = 3


def sample_skills(seed):
    """Uniform independent samples across the published full control bounds."""
    rng = random.Random(seed)
    result = []
    for version in range(2, CANDIDATES + 2):
        controls = {key: rng.uniform(*LIMITS[key]) for key in sorted(LIMITS)}
        result.append(parse_skill(json.dumps({"name": "adaptive_pushing", "version": version,
                                              "control": controls})))
    return result


def run_search(output, sampler_seed=42):
    spec, lock = verify_frozen()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    skills = sample_skills(sampler_seed)
    manifest = {"kind": "conventional_random_search_not_agent_authored",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "sampler": "Python random.Random; uniform per field; sorted field names",
                "sampler_seed": sampler_seed, "evaluation_budget": 4,
                "diagnostic_trials": 0, "candidate_count": CANDIDATES,
                "bounds": LIMITS, "benchmark": lock, "spec": spec,
                "sampler_source_sha256": source_hash(Path(__file__)),
                "sampled_skills": [asdict(skill) for skill in skills]}
    # Preserve all samples and settings before observing any candidate outcomes.
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    skill_dir = output / "sampled_skills"
    skill_dir.mkdir()
    initial_path = skill_dir / "initial.yaml"
    initial_path.write_text(skill_text(load_skill(ROOT / "skills/initial.yaml")), encoding="utf-8")
    paths = [initial_path]
    for skill in skills:
        path = skill_dir / f"random_v{skill.version}.yaml"
        path.write_text(skill_text(skill), encoding="utf-8")
        paths.append(path)
    records = []
    best = None
    for index, path in enumerate(paths):
        label = "initial" if index == 0 else f"random_{index}"
        evaluation = evaluate(path, output / label)
        record = {"label": label, "skill": asdict(load_skill(path)),
                  "skill_sha256": evaluation["skill_sha256"],
                  "aggregate": evaluation["aggregate"]}
        records.append(record)
        if best is None or can_promote(best["aggregate"], record["aggregate"]):
            best = record
        report = {"kind": manifest["kind"], "sampler_seed": sampler_seed,
                  "evaluation_budget": 4, "evaluations_completed": len(records),
                  "benchmark_version": spec["version"],
                  "spec_sha256": source_hash(ROOT / "evaluation/spec.json"),
                  "selected": best["label"],
                  "improved_over_initial": best["label"] != "initial",
                  "selection": "Retain incumbent only when strict score and lexicographic gates both improve",
                  "records": records}
        (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"{label}: successes={record['aggregate']['successes']}/15 "
              f"score={record['aggregate']['score']:.4f}; retained={best['label']}", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sampler-seed", type=int, default=42)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "experiments/random_search" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_search(output, args.sampler_seed)
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
