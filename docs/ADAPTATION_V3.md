# Genuine strategy adaptation under actuator delay

The main milestone is achieved: **a real TrueForge-authored strategy revision
turns failed, unchanged physics-shift tasks into successful tasks**. Validation
improves from 3/21 to 21/21; the first final test improves from 5/25 to 25/25.
The controller primitives are developer-authored. The saved policy selection,
evaluation and promotion are actual agent actions, not a scripted transcript.

[75-second demonstration](../demo/assets/realityshift_adaptation_v3.mp4) ·
[Actual final-test stall/repush](../demo/assets/realityshift_heldout_repush_v3.mp4) ·
[Protocol](V3_PROTOCOL.md) · [Public evidence](evidence/adaptation-v3/experiment/archive.json)

## Original failure and audit

The original nominal controller tracks inverse-kinematics references using fast,
high-gain joint feedback. Under actuator delay, corrective torques arrive after
the state they were intended to correct. Observation histories show persistent
target error, command saturation and repeated velocity/torque reversals. Original
recovery increment 1's five delayed runs never enter pushing; one failed lift
stays at least 258.6 mm from its target with over 97% saturated commands.

The audit also distinguished failed contact acquisition, slow productive pushing,
overshoot and blocked geometry. A nominal replay previously found finger/table
penetration despite a tiny tip-position IK residual. Position-only IK success
does not establish a usable contact pose; local search failure does not prove
global unreachability. These earlier measurements remain in their original
reports and evidence.

The later 19/21 developer controller succeeds on all five existing constant-delay
cases. It is not a new agent result. A fresh three-split development probe found
that it failed all nine mid-task-onset cases: its initial response preference
could return it to direct pushing after the response changed. V3 therefore adds
a bounded stabilization latch following response deterioration or recovery entry.

## Developer infrastructure and focused ablations

Existing bounded primitives remain intact: stabilized approach, backoff/repush,
reachable repositioning, reacquisition, progress-gated tracking memory and
joint-pose braking. The new latch observes marker tracking error; it never reads
delay values, command queues or contact forces. Recovery remains bounded to two
retries and existing phase/sequence deadlines, with the original torque and
episode limits.

Two complete 42-episode development comparisons are preserved:

| Development policy | Original | Developer | Mid-task delayed successes |
| --- | --- | --- | --- |
| Existing progress recovery | 3/21 | 12/21 | 0/9 |
| Response-aware adaptive recovery | 3/21 | 14/21 | 2/9 |

These are developer experiments on development data, not validation or final
outcomes. Both measured source snapshots and all 84 raw episodes are archived.
The earlier progress-memory/braking ablations, including regressions, remain
unchanged in [their report](PROGRESS_RECOVERY.md).

The final agent policy and developer anchor have identical recovery settings
except **approach: stabilized versus adaptive**. This gives a paired approach-mode
comparison: 21/21 versus 14/21 on validation and 25/25 versus 20/25 on the final
test. It does not establish that every primitive was independently necessary in
v3; the agent selected a combination of existing strategies.

## The genuine agent experiment

- Session: `01m6g1asb68209kvmsqs2ma9an`
- Saved agent: `01m6g1amcnk69a5z1n7c42ammp`
- Existing model alias: `nvidia/nemotron-lightning`; no provider/key changes or
  paid-provider fallback.
- Initial full evaluation: `79de82e25376414c9c64c93ea1b2cd91`
- Saved policy: [s0002](../strategies/v3/versions/s0002.yaml), selected and written
  through an actual tool call; its public copy includes the save-call provenance.
- Candidate full evaluation: `98d82cb946424c5281923e999f591348`
- Actual promotion call: accepted; every original successful validation task
  remains successful.

The agent first evaluated the complete baseline, then requested development
trials d02, d03 and d04. These include constant and mid-task response changes.
It saved a recovery policy with stabilized approach, controlled repush,
reposition/correct, stabilized reacquisition, progress-gated memory and pose hold.
Its recorded hypothesis was:

> Stabilized approach with controlled repush and reposition correct will reduce
> oscillation and improve contact acquisition, increasing successes without
> losing baseline.

This is a hypothesis from the actual save call, not an assertion that the agent
identified an exact latency or measured contact forces. It then evaluated the
same 21 validation conditions and called promotion. **No corrective follow-up or
developer choice of the agent's fields was needed in this v3 session.**

The agent used 2/6 full evaluations, 3/12 trials and 1/4 saves. Unused allowances
remain recorded but are closed to mutation by finalization. The conventional
search used all 6/6 validation evaluations. V1/v2 budgets were not reset.

## Paired validation and first final results

| Method | Validation successes | Validation score | Final successes | Final score | Final mean error | Mean squared torque |
| --- | --- | --- | --- | --- | --- | --- |
| Original | 3/21 (14.29%) | 23.6076 | 5/25 (20%) | 29.2083 | 14.6726 cm | 3.58653 |
| Developer adaptive recovery | 14/21 (66.67%) | 66.5727 | 20/25 (80%) | 76.9817 | 3.1624 cm | 0.67816 |
| Conventional search | 14/21 (66.67%) | 66.5727 | 20/25 (80%) | 76.9817 | 3.1624 cm | 0.67816 |
| **TrueForge-selected stabilized recovery** | **21/21 (100%)** | **92.3622** | **25/25 (100%)** | **92.3726** | **0.9486 cm** | **0.02845** |

Validation shifted tasks improve from 0/18 to 18/18; final shifted tasks improve
from 0/20 to 20/20. All nominal tasks remain successful. Final settings use seeds
1000–1004 and nonzero delays of 150/250 ms, absent from selection. The 4.5-second
onset is also new; start-of-episode onset and nominal controls are retained.
The policies were hashed before the first final outcome; all four first final
results are retained without subsequent controller or policy tuning.

The conventional baseline is a predeclared developer anchor plus four seeded
enum samples. Its best policy is the developer anchor, explaining their identical
results. **Its small random draw never sampled the stabilized approach.** The
agent found a useful library choice this draw missed; this does not show that an
LLM beats exhaustive, stratified or adequately covered conventional optimization.
Both methods have a six-evaluation validation cap, but the agent also has optional
development trials. Their total information and compute are not identical.

Mean squared torque is an effort proxy, not energy. Final recovery entries are
0 original, 14 developer, 14 conventional and 1 agent; predictive brake
activations are 0, 17, 17 and 25. Most agent successes prevent failure through
stable tracking and braking, rather than requiring explicit retries.

One actual final success does exercise retry recovery: **h04, seed 1000, 250 ms
constant delay** detects a stall at step 130, selects controlled repush and ends
11.33 mm from the goal. Its full 15-second replay verifies every observation and
applied command against the original archived episode. No successful trajectory
was manufactured for the demonstration.
The observed stages include twenty backoff samples, one repush-stage sample
before the progress criterion resumes ordinary pushing, and sixty-six hold
samples. Measured progress returns control to ordinary pushing.

## Uncertainty and limits of the claim

Descriptive Wilson success intervals are 8.9–39.1% for original, 60.9–91.1% for
developer/conventional and 86.7–100% for the agent. Conditions share starting
seeds, so those intervals must not be interpreted as independent-trial guarantees.
The paired bootstrap resamples whole seed clusters, with only five final seeds.

Against original, the agent's mean final-error difference is −13.72 cm, with a
descriptive seed-cluster 95% interval of −16.90 to −10.94 cm. Its success gain is
80 percentage points in every seed cluster, producing a degenerate observed
bootstrap interval [80, 80]; that is **not zero uncertainty about new environments**.
Against developer/conventional, the success gain is 20 points, with a descriptive
paired cluster interval of 8–32 points. [Post-evaluation paired analysis](evidence/adaptation-v3/paired-analysis.json).

This supports transfer across the tested seeds and interpolated delay/onset
settings. It does not establish robustness to arbitrary dynamics, new robots,
sensor noise, friction, unfamiliar object geometry or physical deployment.
The controller uses a known nominal robot model; contact remains a geometric
hypothesis. There is no clinical validation or claim of safe unsupervised care.

## Changed files and verification

| Area | New implementation |
| --- | --- |
| Observation-triggered response change | `control/response_recovery.py` |
| Tagged enum policy and controller factory | `control/adaptation_schema.py` |
| History-preserving delay onset | `simulation/delay_shift.py` |
| Compact observations and bounded workflow | `agent/adaptation_diagnostics.py`, `agent/adaptation_bridge.py` |
| Real TrueForge integration | `agent/adaptation_server.py`, `agent/configure_adaptation_trueforge.py`, `agent/run_adaptation_v3.py`, `agent/adaptation_instructions.md` |
| Three sets, independent evaluation, conventional search, one-shot final test | `evaluation/v3/` |
| Authentic main and explicit-retry recordings | `demo/adaptation_demo.py`, `demo/heldout_recovery.py`, `demo/adaptation.html`, new demo assets |
| Focused tests | `tests/test_adaptation_v3*.py` |

The suite passes **149 tests**. New checks cover strict schemas, exact constant
delay equivalence, mid-task command history, stabilization latching, baseline-first
enforcement, rejected final/validation probes, immutable saves, real promotion
receipts, corruption/lock behavior, one-shot final reservation, split separation,
paired uncertainty and all public v3 evidence.

Offline verification independently re-scores 42 + 42 development episodes and
271 agent/search/final episodes: **355 new recorded episodes**, including repeated
paired baselines. Those are not 355 independent starting conditions. Public
projections retain real tool calls and remove private model reasoning recursively.

```powershell
python -s -m evaluation.v3.evidence docs/evidence/adaptation-v3/development-first --development
python -s -m evaluation.v3.evidence docs/evidence/adaptation-v3/development-response --development
python -s -m evaluation.v3.evidence docs/evidence/adaptation-v3/experiment
python -s -m pytest -q
```

The original controller, old skills, frozen v1/v2 protocols, earlier held-out
results, TrueForge evidence and budget receipts remain unchanged. Earlier negative
results are linked from the current README; the old README is archived separately.
No old experiment was reset and no failed result was replaced.
The preservation check verifies 119 earlier artifact files unchanged, all three
source locks valid, and the old v2 state/audit equal to their published receipts.
[Preservation receipt](evidence/adaptation-v3/preservation.json).

## Next concrete milestone

Predeclare a larger new-condition experiment with more independent starting
seeds, stronger stratified/exhaustive strategy search and a new untouched final
split. Include object/geometry or friction variation and measure the observation
change detector's false-positive rate. Do not tune on the v3 final settings and
continue calling them unseen. Hardware transfer would then require separate
system identification and physical safety validation.
