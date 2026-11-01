# Reachable recovery follow-up

These are developer-authored controller experiments, not a new TrueForge
adaptation result. The original controller, benchmarks, skills, held-out result
and model-session evidence remain preserved. The v2 stability gate is unchanged.

## Changes and diagnosis

`control/reachable_recovery.py` adds a bounded, goal-directed flank planner and
caches the selected raised/contact joint poses. Lowering checks arrival at the
selected pose rather than the old opposite-side target. One object-displacement
replan is allowed within the existing global timeout. A clearly observed object
jump triggers contact reacquisition immediately; a short horizontal route is
used only when the marker path clears the object. Responsive nominal pushing
retains the original direct law; weak observed response retains stabilization.

The nominal replay in
`evidence/reachable-recovery/table-collision-replay.json` reproduces a failed
crossing recovery: its marker position is attainable but the planned collision
capsules penetrate the table by 68.3 mm. Actual histories show the tip stopping
above the lowering target. This separates blocked contact geometry from delay
tracking error; a small IK position residual is insufficient evidence of a
usable contact pose.

The latest experimental planner checks only collision-enabled robot capsules,
table clearance, original contact-axis orientation and nominal finger/object
distance. It searches at most 45 angle/offset/height combinations. Its geometry
comes from an independent nominal model and observed positions, never shifted
mass, actuator delay, contact forces or intervention metadata. Endpoint checks
and a local solver do not establish collision-free trajectories or global
reachability. Marker clearance is only a heuristic for the horizontal path.

## Measurements

Every attempt uses the same four ablations and 21 development episodes, including
explicit scripted contact, stall and crossing probes. Each bundle preserves all
84 raw trajectories, measured source snapshots, scores and failed gate checks.

| Full variant | Nominal /5 | Mass /5 | Delay /5 | Contact /2 | Stall /2 | Crossing /2 | Total | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Reachable contact, first | 5 | 1 | 3 | 0 | 2 | 0 | 11/21 | 56.1548 |
| Orientation-preserving contact | 5 | 2 | 3 | 1 | 2 | 0 | 13/21 | 63.2153 |
| Table clearance, fixed marker height | 5 | 1 | 3 | 0 | 2 | 0 | 11/21 | 56.2899 |
| Collision-checked contact heights | 5 | 2 | 3 | 2 | 2 | 1 | 15/21 | 70.4943 |

The orientation-preserving version improves the best previous full controller
from 12/21 (59.3720) to 13/21 (63.2153). Its contact seed 0 includes an actual
step-90 reacquisition followed by settling. Its crossing probes still fail.
The stricter fixed-height clearance experiment regresses and is retained.
These are repeatedly inspected development cases, not unseen evaluation.

The final geometry-aware version passes every predeclared stability check. Its
full variant reaches 15/21, versus 12/21 (57.6636) without stabilization, 14/21
(66.7689) without repush and 14/21 (66.6890) without special correction. These
small, reused development samples support retaining the complete strategy;
they do not establish generalization or isolate the grouped stabilization fields.
All four new comparisons preserve 336 episodes, including the regressions.
The passing source and evidence are now locked in `evaluation/v2/frozen.json`.

## Verification

Deterministic tests cover bounded search, force direction, orientation and
collision checks, selected-target arrival, immediate observed separation,
nominal pushing, horizontal path rejection, bounded retries and an exact
table-penetration replay. Archive tests independently re-score every outcome.

TrueForge can now select or revise the bounded strategy enums in a separate
experiment using the existing NVIDIA provider and fresh 6-evaluation,
12-trial, 4-save limits. No aggregate score substitutes for a successful explicit
crossing recovery. The original held-out test is not reopened. Agent outcomes
must be supported by actual session/tool evidence, separately from the
developer-authored 15/21 baseline.

The first real [agent result](STRATEGY_AGENT_RESULT.md) is now preserved: its
candidate regressed to 10/21 and was not promoted. A disclosed corrective
follow-up was needed to obtain the complete matching initial evaluation.
All 121 tests passed: 119 controller/integration/archive tests plus two
additional agent-evidence checks.
