"""Re-score all three recorded developer comparisons offline; no new trials."""
import hashlib
import json
from pathlib import Path
import zipfile

from evaluation.benchmark import ROOT, source_hash
from evaluation.heldout import verify_protocol
from evaluation.metrics import aggregate, score_episode


DIRECTORY = ROOT / "docs/evidence/recovery-v2"


def verify(directory=DIRECTORY):
    spec, _, _, _ = verify_protocol()
    directory = Path(directory)
    index = json.loads((directory / "archive.json").read_text())
    archive = directory / "trajectories.zip"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != index["archive_sha256"]:
        raise ValueError("Recovery archive changed")
    checked = 0
    with zipfile.ZipFile(archive) as bundle:
        for run in ("first", "contact-fix", "final"):
            manifest_path = directory / run / "manifest.json"
            report_path = directory / run / "report.json"
            for path in (manifest_path, report_path):
                if hashlib.sha256(path.read_bytes()).hexdigest() != index["files_sha256"][path.relative_to(directory).as_posix()]:
                    raise ValueError("Recovery report/manifest changed")
            manifest = json.loads(manifest_path.read_text())
            report = json.loads(report_path.read_text())
            if manifest["scoring"] != spec or not report["original_artifacts_unchanged"]:
                raise ValueError("Protocol mismatch")
            if manifest["seeds"] != [0, 1, 2, 3, 4] or manifest["scenarios"] != ["nominal", "high_mass", "actuator_delay"]:
                raise ValueError("Comparison case set differs")
            for name, expected in manifest["source_sha256"].items():
                source = bundle.read(f"{run}/source/{name}").decode("utf-8-sig").replace("\r\n", "\n")
                if hashlib.sha256(source.encode()).hexdigest() != expected:
                    raise ValueError("Archived source differs")
                if run == "final" and source_hash(ROOT / name) != expected:
                    raise ValueError("Current recovery source differs from measured version")
            for label, controller in report["controllers"].items():
                episodes = controller["episodes"]
                expected_pairs = {(s, seed) for s in manifest["scenarios"] for seed in manifest["seeds"]}
                if len(episodes) != 15 or {(e["scenario"], e["seed"]) for e in episodes} != expected_pairs:
                    raise ValueError("Missing or duplicated comparison episodes")
                rescored = []
                for episode in episodes:
                    member = f"{run}/{label}/{episode['scenario']}/seed{episode['seed']}/trajectory.jsonl"
                    data = bundle.read(member)
                    if hashlib.sha256(data).hexdigest() != episode["trajectory_sha256"]:
                        raise ValueError("Recovery trajectory differs")
                    rows = [json.loads(line) for line in data.splitlines()]
                    measured = score_episode(rows, spec)
                    if any(episode[k] != value for k, value in measured.items()):
                        raise ValueError("Recovery score differs from raw trajectory")
                    rescored.append({"scenario": episode["scenario"], **measured})
                    checked += 1
                if aggregate(rescored) != controller["aggregate"]:
                    raise ValueError("Recovery aggregate differs")
                for scenario in manifest["scenarios"]:
                    if aggregate([e for e in rescored if e["scenario"] == scenario]) != controller["by_scenario"][scenario]:
                        raise ValueError("Recovery scenario aggregate differs")
    return {"verified": True, "developer_episodes_rescored": checked,
            "model_calls": 0, "new_simulation_trials": 0}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
