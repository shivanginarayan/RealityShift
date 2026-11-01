from copy import deepcopy
import json
from pathlib import Path

import pytest

from evaluation.benchmark import verify_frozen
from evaluation.metrics import aggregate, can_promote, score_episode


SPEC = json.loads((Path(__file__).parents[1] / "evaluation/spec.json").read_text())


def trajectory(error):
    return [{"step": i, "time_seconds": i * .05,
             "observation_after": [0.] * 17 + [error, 0., -.275, 0., 0., -.323],
             "action": [0.] * 7, "applied_action": [0.] * 7,
             "object_goal_xy_distance": 999, "reward": 999}
            for i in range(1, 301)]


def test_scoring_uses_observations_not_claimed_reward_or_error():
    records = trajectory(.01)
    original = score_episode(records, SPEC)
    for row in records:
        row["reward"] = -1e9
        row["object_goal_xy_distance"] = -1e9
    assert score_episode(records, SPEC) == original
    assert original["success"]
    assert original["score"] == pytest.approx(99.6)


def test_safety_and_complete_episode_are_required():
    rows = trajectory(.01)
    rows[-1]["applied_action"][0] = 2.1
    assert not score_episode(rows, SPEC)["eligible"]
    assert not score_episode(rows[:-1], SPEC)["eligible"]
    rows = trajectory(.01)
    rows[-1]["observation_after"][17] = float("nan")
    assert not score_episode(rows, SPEC)["eligible"]


def test_settling_and_promotion_require_strict_improvement():
    rows = trajectory(.01)
    rows[-2]["observation_after"][17] = .06
    assert not score_episode(rows, SPEC)["success"]
    good = aggregate([score_episode(trajectory(.01), SPEC)])
    bad = aggregate([score_episode(trajectory(.4), SPEC)])
    assert can_promote(bad, good)
    assert not can_promote(good, good)
    unsafe = deepcopy(good)
    unsafe["eligible"] = False
    assert not can_promote(bad, unsafe)


def test_frozen_source_tampering_is_detected(tmp_path):
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation/frozen.json").write_text(json.dumps({"sha256": {"test.py": "wrong"}}))
    (tmp_path / "test.py").write_text("modified")
    with pytest.raises(RuntimeError, match="Frozen benchmark changed"):
        verify_frozen(tmp_path)
