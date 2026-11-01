"""Separate gated v2 MCP endpoint. Does not replace the v1 server on 8765."""
from mcp.server.fastmcp import FastMCP
from agent.strategy_bridge import StrategyBridge

bridge = StrategyBridge()
mcp = FastMCP('RealityShiftStrategiesV2', host='127.0.0.1', port=8766, json_response=True)


@mcp.tool()
def get_status() -> dict:
    """Get stability-gate state, strategy enums, development cases and v2 budgets."""
    return bridge.get_status()


@mcp.tool()
def run_trial(strategy_id: str, case_id: str, seed: int) -> dict:
    """Run a gated v2 development trial with observation-derived diagnostics."""
    return bridge.run_trial(strategy_id, case_id, seed)


@mcp.tool()
def save_candidate_strategy(yaml_text: str, hypothesis: str) -> dict:
    """Save a unique enum-only strategy revision and evidence-based hypothesis."""
    return bridge.save_candidate_strategy(yaml_text, hypothesis)


@mcp.tool()
def get_strategy_diff(strategy_id: str) -> dict:
    """Inspect the saved strategy choices relative to initial."""
    return bridge.get_strategy_diff(strategy_id)


@mcp.tool()
def evaluate_candidate(strategy_id: str) -> dict:
    """Evaluate a strategy under the independently locked v2 development protocol."""
    return bridge.evaluate_candidate(strategy_id)


@mcp.tool()
def promote_strategy(baseline_run_id: str, candidate_run_id: str) -> dict:
    """Promote only authentic evaluated revisions with better measured results."""
    return bridge.promote_strategy(baseline_run_id, candidate_run_id)


if __name__ == '__main__':
    mcp.run(transport='streamable-http')
