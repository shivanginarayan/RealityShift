"""Developer MCP protocol check, not proof of a model-authored agent run."""
import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def check(trial=False):
    async with streamable_http_client("http://127.0.0.1:8765/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            status = await session.call_tool("get_status", {})
            evidence = {"kind": "developer_mcp_smoke_not_model_agent",
                        "tools": [t.name for t in tools.tools],
                        "status": status.model_dump(mode="json")}
            if trial:
                result = await session.call_tool("run_trial", {"skill_id": "initial", "case_id": "case_c", "seed": 0})
                evidence["trial"] = result.model_dump(mode="json")
                if result.isError:
                    raise RuntimeError("MCP diagnostic trial failed")
            path = Path(".runtime/bridge/connection_check.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(f"Connected: {len(tools.tools)} tools; status_error={status.isError}; trial={trial}")
            if status.isError:
                raise RuntimeError("MCP status failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", action="store_true", help="Consumes one diagnostic trial")
    asyncio.run(check(parser.parse_args().trial))
