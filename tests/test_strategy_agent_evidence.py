from evaluation.benchmark import ROOT
from evaluation.strategy_agent_evidence import projection, verify


def test_public_projection_removes_nested_reasoning_but_preserves_tool_calls():
    raw = {'event': {'reasoning_content': 'private', 'result': [
        {'reasoning_content': 'nested', 'tool_call_id': 'real-id', 'content': 'measured'}]}}
    assert projection(raw) == {'event': {'result': [{'tool_call_id': 'real-id', 'content': 'measured'}]}}
    assert raw['event']['reasoning_content'] == 'private'


def test_actual_strategy_session_reports_match_tools_and_saved_trajectories():
    result = verify(ROOT / 'docs/evidence/strategy-v2/agent-session-01m6cj9e')
    assert result['verified'] and result['evaluations'] >= 2
    assert result['episodes_rescored'] >= 45
    assert result['model_calls'] == 0 and result['new_simulation_trials'] == 0
