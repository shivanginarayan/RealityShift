import hashlib
import json
from pathlib import Path

import pytest

from control.skill_schema import load_skill, skill_text
from evaluation import heldout


def test_protocol_separates_development_seeds():
    scoring, _, protocol, _ = heldout.verify_protocol()
    assert not set(scoring["development_seeds"]) & set(protocol["seeds"])
    assert len(protocol["seeds"]) * len(protocol["scenarios"]) == 15


def test_wrong_skill_hash_never_reserves_final_access(tmp_path):
    path = tmp_path / "v2.yaml"
    text = (heldout.ROOT / "skills/initial.yaml").read_text().replace("version: 1", "version: 2")
    path.write_text(text)
    receipt = tmp_path / "receipt.json"
    with pytest.raises(ValueError, match="frozen skill hash"):
        heldout.finalize(path, "wrong", tmp_path / "final", receipt)
    assert not receipt.exists()


def test_final_protocol_pairs_skills_and_refuses_repeat_access(tmp_path, monkeypatch):
    # Synthetic observations only: no held-out simulator episode is executed.
    path = tmp_path / "v2.yaml"
    path.write_text((heldout.ROOT / "skills/initial.yaml").read_text().replace("version: 1", "version: 2"))
    digest = hashlib.sha256(skill_text(load_skill(path)).encode()).hexdigest()
    calls = []

    def synthetic_episode(seed, directory, scenario, skill):
        calls.append((seed, scenario, load_skill(skill).version))
        directory.mkdir(parents=True)
        rows = [{"step": i, "time_seconds": i * .05,
                 "observation_after": [0.] * 17 + [.01, 0., 0., 0., 0., 0.],
                 "action": [0.] * 7, "applied_action": [0.] * 7} for i in range(1, 301)]
        (directory / "trajectory.jsonl").write_text("\n".join(json.dumps(r) for r in rows))

    monkeypatch.setattr(heldout, "run_episode", synthetic_episode)
    output, receipt = tmp_path / "final", tmp_path / "receipt.json"
    result = heldout.finalize(path, digest, output, receipt)
    assert len(calls) == 30
    assert [(s, c) for s, c, _ in calls[:15]] == [(s, c) for s, c, _ in calls[15:]]
    assert not result["improves_on_heldout"]
    with pytest.raises(ValueError, match="already been reserved"):
        heldout.finalize(path, digest, tmp_path / "other-output", receipt)
