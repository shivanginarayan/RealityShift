from pathlib import Path

import pytest

from control.skill_schema import load_skill, parse_skill, skill_text
from control import skill_schema


INITIAL = Path(__file__).parents[1] / "skills/initial.yaml"


def test_initial_skill_roundtrip():
    skill = load_skill(INITIAL)
    assert parse_skill(skill_text(skill)) == skill


@pytest.mark.parametrize("before,after", [
    ("version: 1", "version: true"),
    ("proportional_gain: 60.0", "proportional_gain: .nan"),
    ("max_torque: 2.0", "max_torque: 3.0"),
    ("damping_gain: 4.0", "damping_gain: true"),
    ("action_smoothing: 1.0", "action_smoothing: 0.0"),
    ("version: 1", "version: 1\nversion: 2"),
    ("control:", "scorer: hacked\ncontrol:"),
    ("stop_distance: 0.05", "goal_tolerance: 1.0"),
])
def test_prohibited_or_invalid_skills_rejected(before, after):
    with pytest.raises(ValueError):
        parse_skill(INITIAL.read_text().replace(before, after))


def test_candidates_are_versioned_and_never_overwritten(tmp_path, monkeypatch):
    text = INITIAL.read_text()
    (tmp_path / "skills").mkdir()
    monkeypatch.setattr(skill_schema, "__file__", str(tmp_path / "control/skill_schema.py"))
    with pytest.raises(ValueError, match="at least 2"):
        skill_schema.save_candidate(text)
    path = skill_schema.save_candidate(text.replace("version: 1", "version: 2"))
    assert path == tmp_path / "skills/versions/v0002.yaml"
    assert load_skill(path).version == 2
    with pytest.raises(FileExistsError):
        skill_schema.save_candidate(text.replace("version: 1", "version: 2"))
