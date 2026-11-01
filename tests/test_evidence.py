import hashlib
import json
import zipfile

import pytest

from evaluation.verify_evidence import checked_archive, verify


def test_original_evidence_rescores_and_matches_agent_tool_results():
    result = verify()
    assert result["original_episodes_rescored"] == 92
    assert result["development_promotion_verified"]
    assert not result["heldout_improvement"]


def test_tampered_archive_is_rejected_before_reading(tmp_path):
    path = tmp_path / "bad.zip"
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="archive hash mismatch"):
        checked_archive(path, {"archive_sha256": "original"})


def test_wrong_trace_digest_is_rejected(tmp_path):
    path = tmp_path / "trace.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("trace.jsonl", json.dumps({"step": 1}) + "\n")
    manifest = {"archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "files": {"trace.jsonl": "wrong"}}
    with pytest.raises(ValueError, match="Recorded trajectory changed"):
        checked_archive(path, manifest)
