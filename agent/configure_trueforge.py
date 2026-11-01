"""Register the connector and create an agent using an already configured model."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8790/api/v1"
TOOLS = ["get_status", "run_trial", "save_candidate_skill", "get_skill_diff",
         "evaluate_candidate", "promote_skill"]


def request(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    with urlopen(Request(BASE + path, data=data, headers={"Content-Type": "application/json"}), timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Exact configured provider/model name from TrueForge")
    args = parser.parse_args()
    try:
        existing = request("/settings/mcp-servers/realityshift")
        manifest = existing["data"]["manifest"]
        if manifest.get("url") != "http://127.0.0.1:8765/mcp":
            raise RuntimeError("Existing realityshift connector has a different endpoint")
    except HTTPError as error:
        if error.code != 404:
            raise
        request("/settings/mcp-servers", {"manifest": {
            "type": "remote", "name": "realityshift", "url": "http://127.0.0.1:8765/mcp",
            "description": "Bounded simulated pushing experiments and versioned control skills"}})
    tools = request("/mcp-servers/realityshift/tools")["data"]
    if {tool["name"] for tool in tools} != set(TOOLS):
        raise RuntimeError("Connector does not expose the expected six tools")
    print("Connector verified: six RealityShift tools")
    models = request("/models")["data"]
    if not args.model:
        print("Configured models:", json.dumps(models, indent=2))
        print("Configure OpenAI in the local UI, then rerun with --model provider/model.")
        return
    # The server validates that the exact provider/model reference exists.
    body = {"name": "realityshift-adapter", "description": "Evidence-based simulated pushing skill adaptation",
            "manifest": {"model": {"name": args.model},
              "instructions": Path(__file__).with_name("instructions.md").read_text(),
              "mcp_servers": [{"name": "realityshift", "enable_tools": TOOLS,
                               "preload": True, "require_approval_for_tools": []}],
              "skills": [], "config": {"iteration_limit": 40, "sandbox": {"enabled": False},
                  "dynamic_sub_agents": {"enabled": False}, "generative_ui": {"enabled": False},
                  "web_search": {"enabled": False}, "ask_user_questions": {"enabled": False}}}}
    result = request("/agents", body)
    output = Path(".runtime/bridge/trueforge-agent.json")
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("Created realityshift-adapter; agent record saved locally.")


if __name__ == "__main__":
    main()
