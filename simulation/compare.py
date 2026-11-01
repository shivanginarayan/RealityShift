"""Compare fixed control across paired nominal and shifted development runs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from simulation.nominal import GOAL_TOLERANCE, HORIZON, run_episode
from simulation.scenarios import SCENARIOS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(10)) + [42])
    parser.add_argument("--scenarios", nargs="+", choices=list(SCENARIOS), default=list(SCENARIOS))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds):
        parser.error("Duplicate seeds would inflate episode counts")
    output = args.output or Path("experiments/shifts") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).parents[1]
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "seeds": args.seeds, "scenarios": [SCENARIOS[s].manifest() for s in args.scenarios],
        "horizon": HORIZON, "goal_tolerance_xy_m": GOAL_TOLERANCE, "settle_steps": 10,
        "source_sha256": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in
                          ("control/controller.py", "simulation/nominal.py", "simulation/scenarios.py",
                           "simulation/environment.py", "simulation/delay.py", "simulation/compare.py")},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    report = {}
    for scenario in args.scenarios:
        results = [run_episode(s, output / scenario / f"seed{s}", scenario) for s in args.seeds]
        report[scenario] = {
            "episodes": len(results), "successes": sum(r["success"] for r in results),
            "mean_final_error_xy_m": sum(r["final_error_xy_m"] for r in results) / len(results),
            "results": results,
        }
        print(f"{scenario}: {report[scenario]['successes']}/{len(results)} successes; "
              f"mean error={report[scenario]['mean_final_error_xy_m']:.4f} m", flush=True)
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
