# Gated TrueForge recovery-strategy integration

**Currently blocked by measured developer stability, not by credentials.** The
current v2 prototype is not enabled or promoted. No v2 model session has run.
See [diagnosis, all ablations and failed checks](STRATEGY_RECOVERY_V2.md).

## Strict strategy surface

`control/strategy_schema.py` accepts at most 4 KiB, unique keys, exactly
`name`, integer `version` (1–9999), and four enum selections:

| Field | Choices |
| --- | --- |
| approach | direct, stabilized, adaptive |
| stall | reapproach, controlled_repush |
| overshoot | reapproach, reposition_correct |
| contact | reapproach, stabilized_reacquire |

There are 24 combinations. No code, arbitrary instructions, gain values, paths,
physics settings or scoring changes are accepted. Agent-written candidates must
have a new version >=2. The initial developer skill is
`strategies/v2/initial.yaml`, separate from `skills/initial.yaml` and v1 versions.
Developer primitives and future agent-authored selections are distinct authorship.

## Protocol and tools

`evaluation/v2/spec.json` is a **development draft**, not an activated freeze.
The 21 episodes include known development cases and explicit scripted probes;
there is no claim of genuinely unseen conditions. The scoring rules remain
unchanged; the additional probe episodes make aggregate v2 scores different
comparisons from v1.

The new server is `python -s -m agent.strategy_server` on loopback port **8766**.
The old server remains on 8765. Six v2 tools are implemented:
`get_status`, `run_trial`, `save_candidate_strategy`, `get_strategy_diff`,
`evaluate_candidate`, `promote_strategy`.

Only `get_status` is usable before activation. Experiment operations require a
valid v2 freeze and passed developer gate. Runtime state is isolated under
`.runtime/strategy-v2/`: **6 evaluations including initial, 12 trials, 4 saves**.
Counts survive restart; failed reserved attempts count. An exclusive operation
lock prevents simultaneous processes from overspending. A stale lock requires
inspection, not automatic deletion/reset. Loaded-source checks require restarting
the server after source edits. Candidate/report hashes are verified on promotion,
which requires eligibility, success-first ranking and strict score improvement.
It additionally rejects lower per-case success counts or fewer successful
post-intervention recoveries, so aggregate gains cannot conceal those regressions.

Agent responses expose opaque case IDs, allowed seeds, issued-state diagnostics
and measured outcomes. Applied commands, scenario/physics labels, developer
interventions and source paths are excluded. Trial display is bounded to 14,000
pretty-printed characters. Diagnostic categories distinguish tracking, IK
residual, contact proximity, pushing/settling, and oscillation; they are not
hidden-parameter identification.

## Activation workflow after stable developer evidence exists

The commands below are a future workflow. The current evidence correctly fails
the first command; do not bypass the gate or edit its thresholds after outcomes.

```powershell
python -s -c "from evaluation.v2.evidence import verify; print(verify('docs/evidence/strategy-v2/position-contact', require_current=True))"
python -s -m evaluation.v2.activate --evidence docs/evidence/strategy-v2/position-contact
# Only after a future verified passing gate and one-time freeze:
python -s -m agent.strategy_server
python -s -m agent.configure_strategy_trueforge --model nvidia/nemotron-lightning
python -s -m agent.run_strategy_adaptation
```

Activation re-scores all 84 ablation episodes, verifies current measured sources
and the predeclared gate, then exclusively creates `evaluation/v2/frozen.json`.
The lock covers the new controller/schema/protocol, agent interface/instructions,
and gate evidence. V1/held-out locks remain enforced and unchanged.

Configuration creates a separate `realityshift-strategy-v2` connector and saved
`realityshift-strategy-adapter-v2` agent. It uses the existing NVIDIA model alias,
with no paid-provider fallback or credential changes. Sandbox, external skills,
web, extra connectors, dynamic subagents and questions are disabled. Both
configuration and launch verify the gate **before any TrueForge service request**.
The launcher reserves a session once and refuses implicit duplicate launches or
launches after tool budgets have been used. It preserves agent, benchmark,
session and turn records under the new runtime directory.

Collect a future real session with:

```powershell
python -s -m agent.run_strategy_adaptation --collect .runtime/strategy-v2/agent_runs/RUN
```

Collection uses the existing paginated TrueForge event exporter. Future public
evidence must include actual save/evaluate/promotion calls, failed candidates,
strategy diffs and run IDs, filtered to remove credentials and model reasoning.
Neither a developer MCP check nor a completed model turn proves improvement.
No v1 session, model configuration, experiment state or final receipt is replaced.
