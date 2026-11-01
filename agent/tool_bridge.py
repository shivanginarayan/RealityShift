"""Allowlisted experiment operations with persistent budgets and filtered output."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
from uuid import uuid4

from control.skill_schema import LIMITS, load_skill, parse_skill, skill_text
from evaluation.benchmark import ROOT, evaluate, source_hash, verify_frozen
from evaluation.metrics import can_promote, score_episode
from simulation.nominal import run_episode


# Public opaque development cases. Actual scenario metadata never leaves bridge.
CASES = {"case_a": "nominal", "case_b": "high_mass", "case_c": "actuator_delay"}


class ToolBridge:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.directory = self.root / ".runtime/bridge"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        state_path = self.directory / "state.json"
        self.state = json.loads(state_path.read_text()) if state_path.exists() else {
            "trials": 0, "evaluations": 0, "candidates": 0, "runs": {}, "promoted": "initial"}

    def _audit(self, operation, payload):
        with (self.directory / "audit.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(),
                                     "operation": operation, **payload}, allow_nan=False) + "\n")
        temporary = self.directory / "state.tmp"
        temporary.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        temporary.replace(self.directory / "state.json")

    def _budget(self, key, limit):
        if self.state[key] >= limit:
            raise ValueError(f"{key} budget exhausted")
        self.state[key] += 1
        self._audit("reserve_budget", {"kind": key, "used": self.state[key]})

    def _skill(self, skill_id):
        if skill_id == "initial":
            path = self.root / "skills/initial.yaml"
        elif isinstance(skill_id, str) and re.fullmatch(r"v[0-9]{4}", skill_id):
            path = self.root / "skills/versions" / f"{skill_id}.yaml"
        else:
            raise ValueError("Unknown skill identifier")
        if path.is_symlink() or not path.is_file():
            raise ValueError("Unknown skill identifier")
        if not path.resolve().is_relative_to((self.root / "skills").resolve()):
            raise ValueError("Skill is outside the allowed directory")
        load_skill(path)
        return path

    def get_status(self):
        with self.lock:
            verify_frozen()
            return {"initial_skill": skill_text(load_skill(self._skill("initial"))),
                    "control_bounds": LIMITS, "cases": list(CASES), "seeds": [0, 1, 2, 3, 4],
                    "remaining": {"trials": 12 - self.state["trials"],
                                  "evaluations": 4 - self.state["evaluations"],
                                  "candidates": 4 - self.state["candidates"]},
                    "promoted": self.state["promoted"]}

    def run_trial(self, skill_id, case_id, seed):
        with self.lock:
            spec, _ = verify_frozen()
            if case_id not in CASES or type(seed) is not int or seed not in spec["development_seeds"]:
                raise ValueError("Only listed development cases and seeds are allowed")
            skill = self._skill(skill_id)
            self._budget("trials", 12)
            run_id = uuid4().hex
            output = self.directory / "trials" / run_id
            snapshot = skill_text(load_skill(skill))
            try:
                run_episode(seed, output, CASES[case_id], skill)
                verify_frozen()
                if skill_text(load_skill(skill)) != snapshot:
                    raise ValueError("Skill changed during trial")
                rows = [json.loads(line) for line in (output / "trajectory.jsonl").read_text().splitlines()]
                metrics = score_episode(rows, spec)
                # Explicit allowlist: no applied commands, physics manifest, or source paths.
                telemetry = [{"step": row["step"], "phase": row["phase"],
                              "observation": [round(v, 6) for v in row["observation_after"]],
                              "issued_action": [round(v, 6) for v in row["action"]]}
                             for row in rows[::15] + rows[-1:]]
                result = {"run_id": run_id, "case_id": case_id, "seed": seed,
                          "metrics": metrics, "telemetry": telemetry,
                          "telemetry_precision_decimals": 6,
                          "note": "Displayed telemetry is sampled/rounded; metrics use the full recorded trajectory."}
                if len(json.dumps(result, indent=2)) > 16000:
                    raise ValueError("Diagnostic response exceeds the bounded display size")
                self._audit("trial_completed", {"run_id": run_id, "skill_id": skill_id,
                                                "case_id": case_id, "seed": seed})
                return result
            except Exception:
                self._audit("trial_failed", {"run_id": run_id})
                raise ValueError("Trial failed; developer should inspect local logs") from None

    def save_candidate_skill(self, yaml_text, hypothesis):
        with self.lock:
            verify_frozen()
            if not isinstance(hypothesis, str) or not 20 <= len(hypothesis) <= 2000:
                raise ValueError("Provide a hypothesis of 20–2000 characters")
            skill = parse_skill(yaml_text)
            if not 2 <= skill.version <= 9999:
                raise ValueError("Candidate version must be in [2, 9999]")
            skill_id = f"v{skill.version:04d}"
            directory = self.root / "skills/versions"
            directory.mkdir(parents=True, exist_ok=True)
            if directory.is_symlink() or not directory.resolve().is_relative_to(self.root.resolve()):
                raise ValueError("Invalid candidate directory")
            path = directory / f"{skill_id}.yaml"
            if path.exists() or path.is_symlink():
                raise ValueError("Candidate version already exists")
            self._budget("candidates", 4)
            with path.open("x", encoding="utf-8") as stream:
                stream.write(skill_text(skill))
            self._audit("candidate_saved", {"skill_id": skill_id, "hypothesis": hypothesis,
                                             "skill_sha256": source_hash(path)})
            return {"skill_id": skill_id, "skill": skill_text(skill)}

    def get_skill_diff(self, skill_id):
        with self.lock:
            before = skill_text(load_skill(self._skill("initial")))
            after = skill_text(load_skill(self._skill(skill_id)))
            return {"diff": "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                                        fromfile="initial", tofile=skill_id))}

    def evaluate_candidate(self, skill_id):
        with self.lock:
            verify_frozen()
            path = self._skill(skill_id)
            self._budget("evaluations", 4)
            run_id = uuid4().hex
            output = self.directory / "evaluations" / run_id
            try:
                report = evaluate(path, output)
                self.state["runs"][run_id] = {"skill_id": skill_id,
                    "skill_sha256": report["skill_sha256"], "aggregate": report["aggregate"],
                    "report_sha256": source_hash(output / "report.json")}
                self._audit("evaluation_completed", {"run_id": run_id, "skill_id": skill_id})
                public = [{"case_id": next(k for k, v in CASES.items() if v == e["scenario"]),
                           **{k: v for k, v in e.items() if k != "scenario"}} for e in report["episodes"]]
                return {"run_id": run_id, "metrics": report["aggregate"], "episodes": public}
            except Exception:
                self._audit("evaluation_failed", {"run_id": run_id})
                raise ValueError("Evaluation failed; developer should inspect local logs") from None

    def promote_skill(self, baseline_run_id, candidate_run_id):
        with self.lock:
            verify_frozen()
            runs = self.state["runs"]
            if baseline_run_id not in runs or candidate_run_id not in runs:
                raise ValueError("Both run identifiers must be completed evaluations")
            before, after = runs[baseline_run_id], runs[candidate_run_id]
            if before["skill_id"] != "initial" or after["skill_id"] == "initial":
                raise ValueError("Compare a candidate against the evaluated initial skill")
            for run_id, run in ((baseline_run_id, before), (candidate_run_id, after)):
                report_path = self.directory / "evaluations" / run_id / "report.json"
                if source_hash(report_path) != run["report_sha256"]:
                    raise ValueError("Evaluation evidence changed")
                canonical = skill_text(load_skill(self._skill(run["skill_id"])))
                if hashlib.sha256(canonical.encode()).hexdigest() != run["skill_sha256"]:
                    raise ValueError("Evaluated skill changed")
            accepted = can_promote(before["aggregate"], after["aggregate"])
            if accepted:
                self.state["promoted"] = after["skill_id"]
            self._audit("promotion_decision", {"baseline_run_id": baseline_run_id,
                         "candidate_run_id": candidate_run_id, "accepted": accepted})
            return {"accepted": accepted, "promoted": self.state["promoted"]}
