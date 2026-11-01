# Recovery-capable agent: future integration contract

This is a developer-authored design for a future experiment, not the active
TrueForge instruction pack. The six existing tools still execute frozen v1.
Do not start a new session, reset its budgets, or submit recovery configuration
through the v1 YAML schema.

The first increment adds `control/recovery.py` and an offline diagnostic formatter
in `agent/recovery_diagnostics.py`. Neither is registered in the v1 MCP bridge.
The developer comparison writes a compact, allowlisted diagnostic object per
episode. A future separately versioned bridge can return that object alongside
independently measured metrics, without forwarding complete developer reports.

Interpret the evidence as follows:

- `stall`: little net goal progress and little object displacement over a full
  observation window. It does not establish excessive mass or a particular cause.
- `lost_contact`: persistent fingertip/object separation with little progress.
  It is a geometric hypothesis; there is no force/contact sensor in these inputs.
- `contact_not_acquired`: push entry never established proximity and made no
  progress for two full windows; this is distinct from losing established contact.
- `overshoot`: the object entered the near-goal zone, crossed the goal plane
  along its push-entry direction, then moved farther from the goal.
- `approach_timeout` / `phase_timeout` / `recovery_timeout`: a target or recovery
  sequence could not be completed in its fixed time budget.
- `goal_escape`: the object left the stop region after a hold began.
- `retry_budget_exhausted`: bounded recovery failed; further pushing was stopped.

Future agent work should diagnose a behavioral failure, choose an allowed
strategy, and test that strategy under a new locked protocol. Retain hypotheses,
strategy diffs and per-episode outcomes. Do not claim an inferred cause as a known
physics parameter, count a transition as successful recovery, or claim robust
generalization from existing development cases. Failed retries and regressions
must remain visible.

Before enabling that experiment, define a strict separate strategy schema and
budget, a v2 freeze lock, strategy ablations, and new unseen-condition evaluation
reserved after candidate finalization. Keep the v1 archive and its held-out
receipt intact. Any future agent-selected or agent-written strategies require
real model/tool provenance; the current recovery policy has none and is credited
entirely to the developer.
