import json

import pytest

from agent import run_adaptation as runner
from agent.configure_trueforge import TOOLS


def test_missing_model_never_starts_a_session_or_writes_output(tmp_path, monkeypatch):
    calls = []
    def fake_request(path, body=None):
        calls.append(path)
        return {"data": []}
    monkeypatch.setattr(runner, "request", fake_request)
    with pytest.raises(ValueError, match="No model configured"):
        runner.start(tmp_path / "run")
    assert calls == ["/models"]
    assert not (tmp_path / "run").exists()


def test_agent_with_shell_capability_is_rejected():
    agent = {"manifest": {"mcp_servers": [{"name": "realityshift", "enable_tools": TOOLS}],
                           "config": {"sandbox": {"enabled": True}}}}
    with pytest.raises(ValueError, match="disable sandbox"):
        runner.validate_agent(agent)


def test_trace_export_paginates_and_marks_failed_turn_honestly(tmp_path, monkeypatch):
    (tmp_path / "run.json").write_text(json.dumps({"session_id": "s1", "turn_id": "t1"}))
    def fake_request(path, body=None):
        if "/turns/" in path:
            return {"data": {"state": {"status": "error"}}}
        if "page_token=" not in path:
            return {"data": [{"turn_id": "t1", "event": {"type": "turn.done"}}],
                    "pagination": {"next_page_token": "page2"}}
        return {"data": [{"turn_id": "t1", "event": {"type": "turn.created"}}],
                "pagination": {"next_page_token": None}}
    monkeypatch.setattr(runner, "request", fake_request)
    receipt = runner.collect(tmp_path)
    assert receipt["pages"] == 2 and receipt["event_count"] == 2
    assert receipt["terminal"] and not receipt["successful_turn"]
    assert len((tmp_path / "events.jsonl").read_text().splitlines()) == 2
