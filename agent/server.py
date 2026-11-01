"""RealityShift Streamable HTTP MCP endpoint, bound only to loopback."""
from mcp.server.fastmcp import FastMCP

from agent.tool_bridge import ToolBridge

bridge = ToolBridge()
mcp = FastMCP("RealityShift", host="127.0.0.1", port=8765, json_response=True)


@mcp.tool()
def get_status() -> dict:
    """Get initial skill, allowed controls, opaque development cases and budgets."""
    return bridge.get_status()


@mcp.tool()
def run_trial(skill_id: str, case_id: str, seed: int) -> dict:
    """Run one bounded development trial and return allowed state/action telemetry."""
    return bridge.run_trial(skill_id, case_id, seed)


@mcp.tool()
def save_candidate_skill(yaml_text: str, hypothesis: str) -> dict:
    """Validate and save a new skill version with an evidence-based hypothesis."""
    return bridge.save_candidate_skill(yaml_text, hypothesis)


@mcp.tool()
def get_skill_diff(skill_id: str) -> dict:
    """Compare a saved skill with the initial skill."""
    return bridge.get_skill_diff(skill_id)


@mcp.tool()
def evaluate_candidate(skill_id: str) -> dict:
    """Evaluate initial or candidate skill against the unchanged development suite."""
    return bridge.evaluate_candidate(skill_id)


@mcp.tool()
def promote_skill(baseline_run_id: str, candidate_run_id: str) -> dict:
    """Promote only a verified candidate that improves fixed score and task ranking."""
    return bridge.promote_skill(baseline_run_id, candidate_run_id)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
