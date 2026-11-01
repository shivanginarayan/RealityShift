# RealityShift 2.0: recovery increment 1

This is **developer-authored controller work**, not TrueForge-authored adaptation.
The opt-in implementation is `control/recovery.py`; the original controller,
skill schema, gains, benchmarks, skills, TrueForge evidence and held-out receipt
remain unchanged. No new model-driven experiment was launched.

## Recovery logic

The policy consumes only the 23-value observation and its own phase history,
using an independent nominal model for IK. It never reads shifted-model
parameters, applied commands, rewards or contact sensors.

- **Stall:** a 24-observation window after proximity acquisition has less than
  8 mm net goal progress and less than 20 mm object displacement.
- **Lost contact:** after observing proximity within 65 mm, fingertip/object
  separation exceeds 130 mm for eight observations without useful progress.
  No proximity acquisition and no progress for 48 observations is reported
  separately as `contact_not_acquired`. Contact is a geometric hypothesis.
- **Overshoot:** after entering the 65 mm near-goal region, the object crosses
  the goal plane along the push-entry direction by 15 mm and its error grows
  at least 12 mm. Leaving the 50 mm stop region also triggers recovery.

Recovery holds the current tip target for eight steps, lifts, reapproaches above
the object's current opposite-to-goal side, lowers, then resumes pushing with
fresh detector history. There are at most **two retries**, 35 steps per recovery
phase, 100 steps per sequence and 65 steps per initial approach/lower phase.
Exhaustion stops issuing push targets and applies bounded joint damping. All
commands retain the original torque bound. This is a simulation behavior bound,
not a physical-robot safety guarantee or delay compensation.

`agent/recovery_diagnostics.py` produces compact observation-based hypotheses,
error summaries and bounded transition events. It excludes physics metadata and
applied commands. Online transition events are authoritative for actual policy
decisions; retrospective diagnostics sample post-step observations and may differ
by a step. This formatter is **not registered in the existing MCP bridge**.
`agent/recovery_instructions_v2.md` documents the future integration contract.

## Measured developer comparison

Paired seeds **0–4**, 300 steps, identical initial v1 numeric gains and unchanged
v1 scoring definitions. Nominal is a regression control; these are existing
development scenarios, not unseen conditions. No held-out simulation was run.

| Scenario | v1 successes | Recovery successes | v1 mean final error | Recovery mean final error |
| --- | --- | --- | --- | --- |
| Nominal | 5/5 | 5/5 | 0.01355 m | 0.00610 m |
| High mass | 0/5 | 0/5 | 0.65128 m | 0.28394 m |
| Actuator delay | 0/5 | 0/5 | 0.26086 m | 0.26085 m |

Aggregate score: **35.2412 → 37.3526**; successes remain **5/15**. All 30 final
paired episodes pass the existing finite-state, torque, time and completion
checks. Nominal score slightly regresses, **94.1445 → 93.8491**. All ten shifted
recovery runs exhaust their retries; lower mass-case error does not establish
successful recovery. Delayed tracking still fails to reach recovery targets.
Nominal seed 1 uses two retries and succeeds, although its original trajectory
eventually succeeds without recovery: transient-stall false positives remain.

Three complete development comparisons are preserved (90 episodes). The first
two recovery versions scored 31.5846 and 32.0677 with 4/15 successes. Inspection
found premature contact-loss classification and acquisition time counted as
stall evidence. Separate regression tests cover both fixes. These observations
informed developer fixes; none of these results is an independent final test.
No gain search or agent tuning was performed.

## Validation and next boundary

Tests cover detection/debounce/reset, progress and goal nontriggers, acquisition,
recovery phase order, all retry/time bounds, goal escape, invalid observations,
finite bounded deterministic actions, live-state isolation and compact output.
Archived observations also pin the remaining transient-stall limitation.
The full suite passes **68 tests**. Offline verification re-scores all 90 new
episodes and the original 92 archived episodes without simulation/model calls.
Both original freeze locks pass; original artifacts and budget/receipt hashes
were checked before and after every comparison.

Evidence: [final report](evidence/recovery-v2/final/report.json),
[manifest](evidence/recovery-v2/final/manifest.json),
[archive index](evidence/recovery-v2/archive.json),
[all trajectories and measured source snapshots](evidence/recovery-v2/trajectories.zip).

```powershell
python -s -m evaluation.verify_recovery
python -s -m pytest -q
# Optional new developer run; existing output directories are rejected:
python -s -m evaluation.recovery_comparison --output experiments/recovery-v2/new-run
```

The next useful work is stable observation-based approach/settling behavior and
strategy ablations. Before TrueForge can choose or improve those strategies,
define a separate bounded strategy schema, v2 benchmark lock and experiment
budget. Reserve genuinely unseen shift conditions only after finalization.
Future agent authorship must be supported by actual tool traces; none is claimed
for this increment. The recorded v1 agent result remains a separate result.
