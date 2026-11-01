# TrueForge local integration

The local integration uses TrueForge 0.182.0 and MCP Python SDK 1.30.0.
TrueForge connects to our Streamable HTTP server at `http://127.0.0.1:8765/mcp`.
Both services bind only to loopback. The connector is named `realityshift`.

## Start services

From the project root, install optional agent dependencies:

```powershell
conda activate RealityShift
python -s -m pip install -r requirements-agent-lock.txt
npm install --prefix .runtime/trueforge --save-exact @truefoundry/trueforge@0.182.0
```

In one terminal:

```powershell
python -s -m agent.server
```

In another:

```powershell
.\agent\start_trueforge.ps1
```

The launcher sets `HOST=127.0.0.1`, a project-local SQLite path and the supported
`OUTBOUND_URL_ALLOWED_HOSTS` exception for `127.0.0.1`. TrueForge blocks loopback
connector URLs by default; the exception is needed for this local MCP endpoint.
TrueForge also initializes its normal application-data directory. It may need
permission to create that directory on first startup. Do not expose either port.

Open `http://127.0.0.1:8790`. Under Settings → Models configure OpenAI using your
API key. Enter credentials only in that local settings UI. Runtime databases,
logs and provider settings are ignored by Git under `.runtime/`.

## Configure the agent

```powershell
python -s -m agent.configure_trueforge
```

This registers or verifies the connector, checks all six tools and lists available
configured models. Once a provider is configured, use its exact model reference:

```powershell
python -s -m agent.configure_trueforge --model PROVIDER/MODEL
```

Replace `PROVIDER/MODEL` with an actual configured name from TrueForge. The server
validates it. This creates `realityshift-adapter` with the project instructions,
six explicit MCP tools, no sandbox, no web search, no dynamic subagents, and a
40-iteration turn limit. These bounded tools run without extra approval prompts.
An existing agent is not silently overwritten. Its record is saved locally at
`.runtime/bridge/trueforge-agent.json`.

Start a session with the saved agent and ask it to follow its instructions to
diagnose failures, write a candidate, evaluate it and attempt promotion. Preserve
the TrueForge session/turn IDs and export the real tool trace for sponsor evidence.

Alternatively, start the real run from the command line after configuration:

```powershell
python -s -m agent.run_adaptation
```

The launcher checks model availability, the saved agent's current server-side
configuration, the six-tool allowlist and the frozen benchmark before starting
a turn. It rejects sandbox, dynamic-subagent, web-search and external skill
capabilities. No configured model means no session is created and no model call
is attempted. A start command with a configured provider uses that provider's API
and may incur normal model charges.

It saves agent configuration, benchmark fingerprints, session ID and turn ID
under `.runtime/agent_runs/<timestamp>/`, then returns while TrueForge executes.
Export persisted evidence using the printed directory:

```powershell
python -s -m agent.run_adaptation --collect .runtime/agent_runs/RUN_DIRECTORY
```

The collector saves all paginated session events (newest first), their original
pages, current turn state, a trace hash and an evidence receipt. Running/paused
turns are labeled incomplete; error/cancelled turns are not labeled successful.
Collect again after completion to capture the final trace. Inspect actual skill
evaluation and promotion tool results before claiming improvement: a completed
model turn alone does not establish it. Keep raw traces local and review them
before publishing sponsor evidence. A failed turn-start request may leave a
session record without a confirmed turn ID; inspect that session rather than
blindly launching another paid run.

## Tool boundaries

Tools: `get_status`, `run_trial`, `save_candidate_skill`, `get_skill_diff`,
`evaluate_candidate`, `promote_skill`.

- Only opaque development cases `case_a`–`case_c` and seeds 0–4 are accepted.
- Skills are referenced by `initial` or `vNNNN`; file paths are rejected.
- The agent receives joint states, fingertip/object/goal positions and issued
  actions. Actual mass, delay settings, applied commands and internal artifact
  paths are filtered from tool results.
- Candidate YAML is schema-validated, versioned and never overwritten.
- Budgets persist across restarts: 12 diagnostic trials, 4 candidate saves and
  4 full evaluations, including initial evaluation. One diagnostic trial was
  consumed by the developer connection check; it is labeled as such in evidence.
- Promotion checks actual completed evaluation IDs, report hashes, current skill
  hashes, fixed-source hashes and the evaluator's eligibility/improvement gate.
  Promotion stores the accepted skill ID in bridge state; it does not replace v1.

Run a **single bridge server process**. Threaded calls are serialized with a lock;
the state file is not designed for multiple independent server processes.
Developer artifacts live under `.runtime/bridge/`. Budgets must not be reset
mid-experiment to give a candidate an undisclosed extra evaluation allowance.
Repository write access remains a developer capability, not a tool exposed to the
agent. Hashes alone do not create an operating-system sandbox.

## Verified evidence and current limit

`python -s -m agent.check_connection` performs a real MCP initialize/list/call
sequence. Add `--trial` to execute one actual simulation (consumes a trial).
Connection evidence is saved at `.runtime/bridge/connection_check.json`.
TrueForge connector discovery is saved at
`.runtime/bridge/trueforge-tool-discovery.json`.

Observed: six tools discovered by TrueForge; direct MCP status and a case_c,
seed-0 diagnostic trial completed; 31 tests passed; `pip check` clean. Promotion
tests use synthetic test fixtures and are not claimed as a real improvement.

The initial OpenAI attempt failed with a no-credit error before experiment tools
ran. The configured agent was then switched to `nvidia/nemotron-lightning`, backed
by `nvidia/nemotron-3.5-lightning-30b-a3b` at NVIDIA. It completed two turns,
evaluated three candidates and promoted v4 on development metrics. Frozen v4
regressed on the final unseen-seed comparison. See AGENT_RESULTS.md and
evidence/nemotron/ for actual session IDs, skill hashes and tool traces.
The API key remains in local TrueForge storage and is not committed.

References:

- https://github.com/truefoundry/trueforge
- https://trueforge.dev/quickstart
- https://trueforge.dev/mcp-servers
- https://github.com/modelcontextprotocol/python-sdk/tree/v1.x
