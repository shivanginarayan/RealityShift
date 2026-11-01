"""Developer-only final evaluation, unavailable through the agent tool bridge."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from control.skill_schema import load_skill, skill_text
from evaluation.benchmark import ROOT, source_hash, verify_frozen
from evaluation.metrics import aggregate, can_promote, score_episode
from simulation.nominal import run_episode


def verify_protocol():
    scoring, benchmark = verify_frozen()
    lock = json.loads((ROOT / "evaluation/heldout_frozen.json").read_text())
    for name, expected in lock["sha256"].items():
        if source_hash(ROOT / name) != expected:
            raise RuntimeError("Held-out protocol changed; final evaluation refused")
    protocol = json.loads((ROOT / "evaluation/heldout_spec.json").read_text())
    if set(protocol["seeds"]) & set(scoring["development_seeds"]):
        raise RuntimeError("Held-out seeds overlap development")
    return scoring, benchmark, protocol, lock


def finalize(skill_path, expected_hash, output=None, receipt=None):
    scoring, benchmark, protocol, lock = verify_protocol()
    candidate = load_skill(skill_path)
    if candidate.version < 2:
        raise ValueError("Finalize a candidate version, not the initial skill")
    canonical = skill_text(candidate)
    if hashlib.sha256(canonical.encode()).hexdigest() != expected_hash:
        raise ValueError("Final skill differs from the supplied frozen skill hash")
    output = Path(output) if output else ROOT / "experiments/final"
    receipt = Path(receipt) if receipt else ROOT / ".runtime/heldout-receipt.json"
    if output.exists() or receipt.exists():
        raise ValueError("Final evaluation has already been reserved; refusing repeat access")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    # Reserve before any outcome is visible, including failed/partial attempts.
    with receipt.open("x", encoding="utf-8") as stream:
        json.dump({"reserved_utc": datetime.now(timezone.utc).isoformat(),
                   "skill_sha256": expected_hash, "status": "reserved"}, stream, indent=2)
    output.mkdir(parents=True, exist_ok=False)
    candidate_path = output / "candidate.yaml"
    candidate_path.write_text(canonical, encoding="utf-8")
    initial_path = output / "initial.yaml"
    initial_path.write_text(skill_text(load_skill(ROOT / "skills/initial.yaml")), encoding="utf-8")
    skill_hashes = {p.name: source_hash(p) for p in (initial_path, candidate_path)}
    manifest = {"protocol": protocol, "protocol_lock": lock, "benchmark": benchmark,
                "skill_sha256": skill_hashes,
                "note": "Final unseen-seed evaluation; skill authorship requires separate agent evidence."}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    report = {"protocol": protocol["protocol"], "skills": {}}
    for label, path in (("initial", initial_path), ("candidate", candidate_path)):
        metrics = []
        for scenario in protocol["scenarios"]:
            for seed in protocol["seeds"]:
                verify_protocol()
                if any(source_hash(p) != skill_hashes[p.name] for p in (initial_path, candidate_path)):
                    raise RuntimeError("Final skill snapshots changed")
                directory = output / label / scenario / f"seed{seed}"
                run_episode(seed, directory, scenario, path)
                rows = [json.loads(line) for line in (directory / "trajectory.jsonl").read_text().splitlines()]
                metrics.append({"scenario": scenario, "seed": seed, **score_episode(rows, scoring)})
        report["skills"][label] = {"aggregate": aggregate(metrics), "episodes": metrics}
    verify_protocol()
    report["improves_on_heldout"] = can_promote(report["skills"]["initial"]["aggregate"],
                                               report["skills"]["candidate"]["aggregate"])
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    receipt.write_text(json.dumps({"status": "completed", "skill_sha256": expected_hash,
                                   "report_sha256": source_hash(output / "report.json")}, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", type=Path, required=True)
    parser.add_argument("--skill-sha256", required=True, help="Canonical skill hash from final development evaluation")
    args = parser.parse_args()
    result = finalize(args.skill, args.skill_sha256)
    print(json.dumps({k: v["aggregate"] for k, v in result["skills"].items()}, indent=2))
