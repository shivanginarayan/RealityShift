"""New v3-only loopback endpoint; old MCP servers and their budgets unchanged."""
from mcp.server.fastmcp import FastMCP
from agent.adaptation_bridge import AdaptationBridge

bridge = AdaptationBridge()
mcp = FastMCP('RealityShiftAdaptationV3', host='127.0.0.1', port=8767, json_response=True)


@mcp.tool()
def get_status() -> dict:
    """Get strict strategy choices, catalog, opaque development cases and budgets."""
    return bridge.get_status()


@mcp.tool()
def run_trial(strategy_id: str, condition_id: str) -> dict:
    """Observe one listed development task with compact behavior diagnostics."""
    return bridge.run_trial(strategy_id, condition_id)


@mcp.tool()
def save_candidate_strategy(yaml_text: str, hypothesis: str) -> dict:
    """Persist a bounded strategy revision after the full initial baseline."""
    return bridge.save_candidate_strategy(yaml_text, hypothesis)


@mcp.tool()
def get_strategy_diff(strategy_id: str) -> dict:
    """Inspect actual saved choices against the original policy."""
    return bridge.get_strategy_diff(strategy_id)


@mcp.tool()
def evaluate_candidate(strategy_id: str) -> dict:
    """Evaluate all paired validation tasks. Initial baseline is required first."""
    return bridge.evaluate_candidate(strategy_id)


@mcp.tool()
def promote_strategy(baseline_run_id: str, candidate_run_id: str) -> dict:
    """Promote only independently measured improvement with no lost baseline success."""
    return bridge.promote_strategy(baseline_run_id, candidate_run_id)


if __name__ == '__main__':
    mcp.run(transport='streamable-http')
