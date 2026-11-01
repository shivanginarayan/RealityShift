import hashlib
import json

import pytest

from demo.render_replay import Replay
from simulation.nominal import run_episode


@pytest.fixture
def recording(tmp_path):
    run_episode(0, tmp_path)
    return tmp_path


def test_replay_reproduces_recorded_observations_without_controller(recording):
    with Replay(recording) as replay:
        for _ in replay.rows:
            replay.advance()
        assert replay.index == 300


def test_modified_trajectory_is_rejected(recording):
    with (recording / "trajectory.jsonl").open("a") as stream:
        stream.write("{}\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        Replay(recording)


def test_claimed_outcome_cannot_override_measured_result(recording):
    path = recording / "summary.json"
    summary = json.loads(path.read_text())
    summary["success"] = not summary["success"]
    path.write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="independently scored"):
        Replay(recording)
