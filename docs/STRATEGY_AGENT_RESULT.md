# First v2 strategy-agent result

The developer controller improved to **15/21, score 70.4943**. The actual
NVIDIA-backed TrueForge revision achieved **10/21, score 50.5328** and was not
promoted. This is a negative adaptation result, not evidence of agent improvement
or unseen-condition generalization.

Session `01m6cj9e08f1bthk34h5xgzqw5` used the separate saved v2 agent, six-tool
allowlist and frozen recovery baseline. No provider or credential was changed.
The agent saved `s0002`, changing approach from `adaptive` to `stabilized` and
stall handling from `controlled_repush` to `reapproach`. Its hypothesis discussed
the approach change but omitted the simultaneous stall change; the actual diff
and evaluated YAML are preserved.

| Strategy | Nominal /5 | Mass /5 | Delay /5 | Contact /2 | Stall /2 | Crossing /2 | Total | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Developer initial | 5 | 2 | 3 | 2 | 2 | 1 | 15/21 | 70.4943 |
| Agent s0002 | 3 | 2 | 3 | 0 | 1 | 1 | 10/21 | 50.5328 |

The first turn ran three initial diagnostics, saved/evaluated s0002, and stopped.
It incorrectly described 1/3 trial successes versus 10/21 candidate successes as
an improvement, despite instructions to evaluate the full baseline. Some causal
claims about IK feasibility and force contact also exceeded the observations.
Those statements remain in the preserved transcript; they are not endorsed.

A **developer-supervised corrective follow-up in the same session** required
the missing complete initial evaluation and a matching-case comparison. The
agent then evaluated initial, recognized the regression and stopped. The full
interaction therefore must not be presented as unassisted autonomous adaptation.
No `promote_strategy` call occurred; the bridge still records `initial`.

Actual completed evaluation IDs:

- s0002: `97e62296adf349f4b89bfbfe1db351e6`
- initial: `ed88a41c5a7249e68bf3371e043ad6bd`

Budgets used: two evaluations, three trials, one save. Remaining: **4/9/3**.
No budgets were reset. No new held-out evaluation was opened. Original v1
artifacts, session, promoted numeric skill and exhausted evaluation budget remain
unchanged. The first-turn failure is retained alongside the corrective turn.

[Public evidence](evidence/strategy-v2/agent-session-01m6cj9e/archive.json) contains
actual tool events, saved agent configuration, supervision prompt, audit/state
receipts and 45 raw trajectories. Private model reasoning is recursively removed
from public event projections; original exports remain local with receipt hashes.

```powershell
python -s -m evaluation.strategy_agent_evidence docs/evidence/strategy-v2/agent-session-01m6cj9e
```

This checks saved scores against raw observations, strategy/report hashes,
evaluation tool-call IDs/responses and budget reservations, without simulator or
model calls. Future agent work should enforce a complete baseline before candidate
evaluation in a new protocol, and test whether diagnostic-guided strategy choice
beats this frozen baseline. The existing v2 lock is preserved.
