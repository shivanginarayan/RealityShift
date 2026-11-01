import json
from pathlib import Path

import pytest

from agent.tool_bridge import ToolBridge
from agent import tool_bridge
from control.skill_schema import load_skill, skill_text
from evaluation.benchmark import source_hash
import hashlib


@pytest.fixture
def bridge(tmp_path):
    (tmp_path / "skills").mkdir()
    initial = Path(__file__).parents[1] / "skills/initial.yaml"
    (tmp_path / "skills/initial.yaml").write_text(initial.read_text())
    return ToolBridge(tmp_path)


def test_skill_paths_and_candidate_overwrites_rejected(bridge):
    for identifier in ("../evaluation/spec.json", "v0002/../../x", "v2", "v0002.yaml"):
        with pytest.raises(ValueError):
            bridge._skill(identifier)
    text = bridge.get_status()["initial_skill"].replace("version: 1", "version: 2")
    result = bridge.save_candidate_skill(text, "Test hypothesis about command smoothing.")
    assert result["skill_id"] == "v0002"
    with pytest.raises(ValueError, match="already exists"):
        bridge.save_candidate_skill(text, "Test hypothesis about command smoothing.")
    assert "version: 2" in bridge.get_skill_diff("v0002")["diff"]


def test_budget_persists_across_restarts(bridge):
    bridge.state["trials"] = 12
    bridge._audit("test", {})
    restarted = ToolBridge(bridge.root)
    assert restarted.get_status()["remaining"]["trials"] == 0
    with pytest.raises(ValueError, match="budget exhausted"):
        restarted.run_trial("initial", "case_a", 0)


def test_only_development_cases_and_seeds_allowed(bridge):
    for case, seed in (("high_mass", 0), ("case_b", 42), ("case_b", True)):
        with pytest.raises(ValueError):
            bridge.run_trial("initial", case, seed)
    assert bridge.state["trials"] == 0


def test_real_trial_filters_hidden_metadata(bridge):
    result = bridge.run_trial("initial", "case_c", 0)
    assert len(result["telemetry"]) == 31
    serialized = json.dumps(result)
    for forbidden in ("developer_physics_manifest", "mass_scale", "delay_steps", "applied_action", "actuator_delay"):
        assert forbidden not in serialized
    assert "observation" in result["telemetry"][0]


def test_promotion_requires_real_completed_evaluation_ids(bridge):
    with pytest.raises(ValueError, match="completed evaluations"):
        bridge.promote_skill("fake", "fake2")


def test_promotion_checks_evidence_and_persists_acceptance(bridge, monkeypatch):
    text = bridge.get_status()["initial_skill"].replace("version: 1", "version: 2")
    bridge.save_candidate_skill(text, "Test hypothesis about smoother commands.")

    def fake_evaluate(path, output):
        output.mkdir(parents=True)
        candidate = load_skill(path).version == 2
        metrics = {"eligible": True, "rank": [1 if candidate else 0, -.01, -1],
                   "score": 90 if candidate else 10}
        report = {"skill_sha256": hashlib.sha256(skill_text(load_skill(path)).encode()).hexdigest(),
                  "aggregate": metrics, "episodes": []}
        (output / "report.json").write_text(json.dumps(report))
        return report

    monkeypatch.setattr(tool_bridge, "evaluate", fake_evaluate)
    baseline = bridge.evaluate_candidate("initial")["run_id"]
    candidate = bridge.evaluate_candidate("v0002")["run_id"]
    assert bridge.promote_skill(baseline, candidate)["accepted"]
    assert ToolBridge(bridge.root).state["promoted"] == "v0002"
    report = bridge.directory / "evaluations" / candidate / "report.json"
    report.write_text("tampered")
    with pytest.raises(ValueError, match="evidence changed"):
        bridge.promote_skill(baseline, candidate)
