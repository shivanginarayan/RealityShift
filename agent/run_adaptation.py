"""Start a real TrueForge turn and collect its persisted provenance separately."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

from agent.configure_trueforge import TOOLS, request
from evaluation.benchmark import ROOT, verify_frozen


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def validate_agent(agent):
    manifest = agent["manifest"]
    servers = manifest.get("mcp_servers", [])
    if len(servers) != 1 or servers[0]["name"] != "realityshift":
        raise ValueError("Agent must use only the RealityShift connector")
    if set(servers[0].get("enable_tools", [])) != set(TOOLS):
        raise ValueError("Agent must enable exactly the six bounded RealityShift tools")
    config = manifest.get("config", {})
    for field in ("sandbox", "dynamic_sub_agents", "web_search", "generative_ui"):
        if config.get(field, {}).get("enabled") is not False:
            raise ValueError(f"Agent must explicitly disable {field}")
    if manifest.get("skills"):
        raise ValueError("External instruction-pack skills are not allowed for this run")
    if not 1 <= config.get("iteration_limit", 0) <= 40:
        raise ValueError("Agent iteration limit must be between 1 and 40")


def start(output=None, agent_record=None):
    _, frozen = verify_frozen()
    if not request("/models")["data"]:
        raise ValueError("No model configured. Configure OpenAI in TrueForge Settings → Models first.")
    record_path = Path(agent_record) if agent_record else ROOT / ".runtime/bridge/trueforge-agent.json"
    if not record_path.is_file():
        raise ValueError("Create the saved agent with python -s -m agent.configure_trueforge --model PROVIDER/MODEL")
    saved = json.loads(record_path.read_text())
    agent = request(f"/agents/{saved['data']['id']}")["data"]
    validate_agent(agent)
    tools = request("/mcp-servers/realityshift/tools")["data"]
    if {t["name"] for t in tools} != set(TOOLS):
        raise ValueError("RealityShift connector tools differ from expected configuration")
    output = Path(output) if output else ROOT / ".runtime/agent_runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "agent.json", agent)
    write_json(output / "benchmark.json", frozen)
    session = request("/sessions", {"agent": {"name": agent["name"]}})["data"]
    run = {"session_id": session["id"], "agent_id": agent["id"],
           "started_utc": datetime.now(timezone.utc).isoformat(), "status": "session_created"}
    write_json(output / "run.json", run)
    turn = request(f"/sessions/{session['id']}/turns", {"stream": False, "input": [{
        "type": "user.message", "content": "Follow your RealityShift instructions. Establish Run 1, diagnose failures using bounded probes, save and evaluate a candidate skill, and attempt promotion only when the fixed improvement gate passes. Report all measured outcomes and run IDs honestly."}]})["data"]
    run.update({"turn_id": turn["id"], "status": turn["state"]["status"]})
    write_json(output / "run.json", run)
    return output, run


def collect(directory):
    directory = Path(directory)
    run = json.loads((directory / "run.json").read_text())
    if "turn_id" not in run:
        raise ValueError("No confirmed turn ID; inspect saved session before starting another turn")
    session_id, turn_id = run["session_id"], run["turn_id"]
    turn = request(f"/sessions/{session_id}/turns/{turn_id}")["data"]
    events, pages, tokens = [], [], set()
    token = None
    while True:
        query = {"limit": 100, "last_turn_id": turn_id}
        if token:
            query["page_token"] = token
        page = request(f"/sessions/{session_id}/events?{urlencode(query)}")
        pages.append(page)
        events.extend(page["data"])
        token = page["pagination"].get("next_page_token")
        if not token:
            break
        if token in tokens or len(pages) >= 100:
            raise RuntimeError("Event pagination did not terminate; evidence not marked complete")
        tokens.add(token)
    # API returns newest first; preserve API order and explicit pagination metadata.
    trace = directory / "events.jsonl"
    trace.write_text("".join(json.dumps(e, allow_nan=False) + "\n" for e in events), encoding="utf-8")
    write_json(directory / "event-pages.json", pages)
    write_json(directory / "turn.json", turn)
    status = turn["state"]["status"]
    receipt = {"kind": "trueforge_session_export", "session_id": session_id, "turn_id": turn_id,
               "status": status, "terminal": status in ("done", "error", "cancelled"),
               "successful_turn": status == "done", "event_count": len(events), "pages": len(pages),
               "exported_utc": datetime.now(timezone.utc).isoformat(),
               "trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
               "note": "Session completion alone does not prove skill improvement. Inspect tool outcomes."}
    write_json(directory / "evidence.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", type=Path, help="Export current evidence from an existing run directory")
    args = parser.parse_args()
    try:
        if args.collect:
            print(json.dumps(collect(args.collect), indent=2))
        else:
            output, run = start()
            print(json.dumps(run, indent=2))
            print(f"Collect evidence with: python -s -m agent.run_adaptation --collect {output}")
    except ValueError as error:
        parser.exit(2, str(error) + "\n")
