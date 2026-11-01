"""Re-score original published trajectories without API calls or simulation."""
import hashlib
import json
import math
from pathlib import Path
import zipfile

from control.skill_schema import load_skill, parse_skill, skill_text
from evaluation.benchmark import ROOT, source_hash, verify_frozen
from evaluation.heldout import verify_protocol
from evaluation.metrics import aggregate, can_promote, score_episode
from agent.run_adaptation import validate_agent

EVIDENCE = ROOT / "docs/evidence/nemotron"


def equivalent(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and set(actual) == set(expected) and all(
            equivalent(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            equivalent(a, b) for a, b in zip(actual, expected))
    if type(expected) in (int, float) and type(actual) in (int, float):
        return math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
    return type(actual) is type(expected) and actual == expected


def checked_archive(path, manifest):
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["archive_sha256"]:
        raise ValueError("Trajectory archive hash mismatch")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(manifest["files"]):
            raise ValueError("Archive entries differ from manifest")
        if sum(i.file_size for i in archive.infolist()) > 128 * 1024 * 1024:
            raise ValueError("Trajectory archive exceeds verification size bound")
        records = {}
        for name in names:
            # Read directly; never extract paths supplied by an archive.
            data = archive.read(name)
            if hashlib.sha256(data).hexdigest() != manifest["files"][name]:
                raise ValueError(f"Recorded trajectory changed: {name}")
            records[name] = [json.loads(line) for line in data.decode("utf-8").splitlines()]
        return records


def verify():
    spec, _ = verify_frozen()
    verify_protocol()
    manifest = json.loads((EVIDENCE / "trace-archive.json").read_text())
    rows = checked_archive(EVIDENCE / manifest["archive"], manifest)
    summary = json.loads((EVIDENCE / "summary.json").read_text())
    agent = json.loads((EVIDENCE / "agent-configuration.json").read_text())
    validate_agent(agent)
    if agent["manifest"]["model"]["name"] != "nvidia/nemotron-lightning":
        raise ValueError("Published agent does not use the recorded NVIDIA model")
    reports = {}
    checked = 0
    for name, expected in manifest["source_reports_sha256"].items():
        if source_hash(EVIDENCE / name) != expected:
            raise ValueError(f"Published report changed: {name}")
        reports[name] = json.loads((EVIDENCE / name).read_text())

    def rescore(report, prefix):
        nonlocal checked
        values = []
        for episode in report["episodes"]:
            name = f"{prefix}/{episode['scenario']}/seed{episode['seed']}.jsonl"
            metrics = score_episode(rows[name], spec)
            recorded = {k: v for k, v in episode.items() if k not in ("seed", "scenario")}
            if not equivalent(metrics, recorded):
                raise ValueError(f"Recomputed metrics differ: {name}")
            values.append(metrics)
            checked += 1
        result = aggregate(values)
        if not equivalent(result, report["aggregate"]):
            raise ValueError(f"Recomputed aggregate differs: {prefix}")
        return result

    development = {}
    for evaluation in summary["evaluations"]:
        skill_id = evaluation["skill_id"]
        report = reports[f"{skill_id}-development.json"]
        path = ROOT / ("skills/initial.yaml" if skill_id == "initial" else f"skills/versions/{skill_id}.yaml")
        digest = hashlib.sha256(skill_text(load_skill(path)).encode()).hexdigest()
        if digest != evaluation["skill_sha256"] or digest != report["skill_sha256"]:
            raise ValueError("Evaluated skill hash does not match saved YAML")
        development[skill_id] = rescore(report, f"development/{skill_id}")
    final = reports["heldout-report.json"]
    heldout = {label: rescore(report, f"heldout/{label}") for label, report in final["skills"].items()}
    if can_promote(heldout["initial"], heldout["candidate"]) != final["improves_on_heldout"]:
        raise ValueError("Held-out gate disagrees with recorded outcome")
    for diagnostic in json.loads((EVIDENCE / "diagnostic-results.json").read_text()):
        metrics = score_episode(rows[f"diagnostics/{diagnostic['run_id']}.jsonl"], spec)
        if not equivalent(metrics, diagnostic["metrics"]):
            raise ValueError("Diagnostic metrics differ")
        checked += 1

    events = [json.loads(line) for line in (EVIDENCE / "session-tools.jsonl").read_text().splitlines()]
    responses = {e["event"]["tool_call_id"]: e["event"]["content"]
                 for e in events if e["event"]["type"] == "tool.response"}
    saved, evaluated, promoted = set(), set(), False
    for event in events:
        for call in event["event"].get("tool_calls", []):
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"])
            # Diagnostic response in the original session was replaced by the
            # harness's plain-text size-limit notice. Preserve that limitation.
            if name not in ("save_candidate_skill", "evaluate_candidate", "promote_skill"):
                continue
            response = json.loads(responses[call["id"]])
            if name == "save_candidate_skill":
                skill = parse_skill(args["yaml_text"])
                skill_id = f"v{skill.version:04d}"
                if skill != load_skill(ROOT / f"skills/versions/{skill_id}.yaml") or not args["hypothesis"]:
                    raise ValueError("Agent-authored skill or hypothesis differs from evidence")
                saved.add(skill_id)
            elif name == "evaluate_candidate":
                if not equivalent(response["metrics"], development[args["skill_id"]]):
                    raise ValueError("TrueForge evaluation response disagrees with recomputed score")
                evaluated.add(args["skill_id"])
            elif name == "promote_skill":
                by_id = {r["run_id"]: r for r in summary["evaluations"]}
                baseline = by_id[args["baseline_run_id"]]
                candidate = by_id[args["candidate_run_id"]]
                accepted = can_promote(development[baseline["skill_id"]], development[candidate["skill_id"]])
                if accepted != response["accepted"] or response["promoted"] != summary["promoted"]:
                    raise ValueError("TrueForge promotion decision differs")
                promoted = accepted
    if saved != {"v0002", "v0003", "v0004"} or evaluated != set(development) or not promoted:
        raise ValueError("Relevant agent tool evidence is incomplete")
    return {"verified": True, "original_episodes_rescored": checked,
            "api_calls": 0, "new_simulation_trials": 0,
            "development": development, "heldout": heldout,
            "development_promotion_verified": promoted,
            "heldout_improvement": final["improves_on_heldout"]}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, allow_nan=False))
