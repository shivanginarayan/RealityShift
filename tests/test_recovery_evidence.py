import json
import zipfile

from control.recovery import FailureDetector
from evaluation.verify_recovery import DIRECTORY, verify


def test_developer_comparison_is_reproducible_from_original_bytes():
    result = verify()
    assert result == {"verified": True, "developer_episodes_rescored": 90,
                      "model_calls": 0, "new_simulation_trials": 0}


def test_recorded_nominal_acquisition_is_not_misclassified_as_lost_contact():
    # Real observation replay is deterministic and starts no simulator/model.
    detector = FailureDetector()
    with zipfile.ZipFile(DIRECTORY / "trajectories.zip") as bundle:
        data = bundle.read("final/original_v1/nominal/seed1/trajectory.jsonl")
    reasons = []
    for row in map(json.loads, data.splitlines()):
        if row["phase"] != "push":
            detector.reset()
        else:
            reason = detector.update(row["observation_before"])
            if reason:
                reasons.append((row["step"], reason))
    # Residual limitation: a transient stall is still detected in a run that
    # later succeeds. Preserve this observation rather than hiding it.
    assert reasons == [(step, "stall") for step in range(71, 75)]
