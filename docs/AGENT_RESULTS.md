# Recorded Nemotron adaptation results

A real TrueForge-managed agent using NVIDIA's
`nvidia/nemotron-3.5-lightning-30b-a3b` generated three persistent YAML control
skills. V4 improved the fixed development benchmark and passed promotion.
It did not improve the final unseen-seed benchmark. This is simulated physics
adaptation with limited evidence, not real-hardware transfer.

## Development outcomes

| Skill | Successes | Fixed score | Outcome |
| --- | --- | --- | --- |
| Initial v1 | 5/15 | 35.2412 | Baseline |
| Agent v2 | 4/15 | 28.9703 | Not promoted |
| Agent v3 | 5/15 | 34.6072 | Not promoted |
| Agent v4 | 6/15 | 41.8346 | Promoted |
| Conventional random-search best | 6/15 | 44.6180 | Higher than agent score |

The agent used four full evaluations total, including initial. One diagnostic
episode was agent-requested; one earlier developer smoke trial is also counted in
bridge state. Budgets were never reset. The failed first candidate was preserved.
A developer follow-up asked the same session to use its remaining budget, without
supplying candidate parameter values. All three candidate YAML files were written
through the agent's save tool, not manually revised by the developer.

The changes are bounded numeric controller adjustments. V4 adjusts gain,
approach geometry, push offset, stopping distance and command smoothing; it does
not introduce a new recovery algorithm. Diagnostic depth was limited: the agent
did not use additional probes during its continuation. The random-search result
prevents claiming superiority over simple optimization.

## Final unseen-seed outcomes

After budget exhaustion and v4 promotion, the developer froze its evaluated hash
`958115f2e8ba6ae1f8475f0616235a9e4001fed71c43c9202b68538e17073014`
and executed the reserved final protocol once.

| Skill | Successes | Fixed score | Mean final XY error |
| --- | --- | --- | --- |
| Initial v1 | 5/15 | 36.4483 | 0.2300 m |
| Frozen agent v4 | 5/15 | 34.6993 | 0.3050 m |

Both suites remained eligible under the fixed action/finite-state guards. V4's
development improvement did not generalize to these unseen seeds. The final
report's improvement gate returned false. Do not tune further against these seeds
and continue describing them as held out. The four-evaluation experiment budget
is exhausted; additional experiments must be disclosed separately.

## Evidence and reproduction

TrueForge session: `01m6b09r6y75stas7g5nx86bna`.
Turns: `01m6b09r83a6ktm9cf7y1k5fj0` and `01m6b0ht9s7r5rwyg8xgwf3dg3`.

`evidence/nemotron/summary.json` records tool run IDs, skill/report hashes, budget
usage and original/filtered trace hashes. `session-tools.jsonl` preserves tool
calls, responses and event metadata while omitting model prose, reasoning content
and user message bodies. The four development reports and final held-out report
and pre-run manifest are included. API credentials and local runtime databases
are not included. Complete raw trajectories remain local generated artifacts.

Reproduce development evaluation of the saved v4 without calling a model:

```powershell
python -s -m evaluation.benchmark --skill skills/versions/v0004.yaml
python -s -m pytest -q
```

Final evaluation intentionally refuses repeat execution in the original workspace.
Fresh-checkout reproduction can follow HELDOUT.md; it is replication, not a new
unseen test. The frozen evaluator, thresholds and original skill remain unchanged.
Shelled implementation provenance and event-submission compliance remain pending.
