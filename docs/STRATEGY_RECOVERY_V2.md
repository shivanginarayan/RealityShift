# Recovery diagnosis and distinct strategy experiments

**Status: developer research; v2 agent experiments remain disabled.** Three
complete ablations (252 new developer episodes) are retained. No TrueForge model
was called, no new agent-authored improvement is claimed, and no unseen-condition
evaluation occurred. V1 and both earlier recovery increments remain unchanged.

## What the histories establish

`evaluation/recovery_diagnosis.py` reconstructs the original recovery targets by
replaying phase logic against archived observations, checking every recorded
phase. No simulator steps or IK calls are needed for this reconstruction.
[Thirty-episode diagnosis](evidence/strategy-v2/diagnosis-before.json).

| Failure type | Observation-based distinction and actual example |
| --- | --- |
| Approach tracking | All five increment-1 delay runs never enter `push`. Failed lift segments have median target errors around 0.18–0.41 m and mostly 91–97% saturated joint commands. Seed 1's first lift remains at least 0.25858 m away. This is not evidence of a stalled object. |
| Contact acquisition | A run enters `push` but never records fingertip/object proximity within 65 mm during that phase. The second experiment's mass cases 0, 1, 2 and 4 contain this pattern. Object motion during approach/lowering does not establish successful pushing contact. |
| Pushing/settling | Proximity is observed but final-ten-step settling fails. Increment-2 nominal seed 3 ends 3.86 cm away but reaches tolerance too late; final distance alone would falsely label it successful. |
| Control oscillation | Joint-velocity and issued-torque sign reversals coexist with persistent target error and saturation. This appears in the failed delay runs and some successful nominal runs: oscillation alone neither identifies latency nor proves terminal failure. |
| Nominal IK objective/feasibility | A separate exact controller replay shows an opposite-side target with 0.09583 m nominal IK residual and 0.09684 m actual tip error. Position-only IK still leaves about 0.09483 m residual. Slower tracking cannot remove that residual; a bounded local solve does not prove global unreachability. |

[Nominal-IK replay evidence](evidence/strategy-v2/ik-replay.json) uses the archived
second-experiment controller, with no simulator steps. New trajectories record
both nominal IK residual and joint reference error alongside actual target error.
Diagnostics never require shifted physics parameters, applied actions or force
sensors. Contact/proximity and causal diagnoses remain hypotheses.

## Distinct developer-authored maneuvers

`control/strategies.py` implements independently selectable primitives:

- **Stabilized approach/reacquisition:** bounded nominal inverse dynamics,
  three-observation arrival checks and a twelve-step stabilization stage. Adaptive
  mode begins with six gentle steps and uses early observed joint response;
  sustained poor tracking can also switch modes. It receives no scenario ID or
  simulator latency value. Responsive free-space motion and controlled contact
  tracking are distinct modes in the latest experimental variant.
- **Controlled repush:** back off 7 cm without lifting, then advance a persistent
  Cartesian waypoint by at most 8 mm per update, at most 4 cm ahead of the tip.
  Resume pushing after measured progress; escalate after forty unsuccessful
  steps. This differs from lifting and walking around the object.
- **Reposition-and-correct:** stabilize, lift, recompute the opposite side from
  current object/goal geometry, approach a fixed waypoint, lower, and make a
  bounded corrective push. A segment-crossing detector catches overshoot when
  sampling skips the near-goal region. Recovery positioning uses position-first
  nominal IK; unresolved IK residuals remain visible rather than counted as
  successful arrival.

All maneuvers retain two retries, bounded phases/sequence duration, finite
observations and the original torque limit. They remain experimental and do not
replace the active v1 controller or recorded promoted skill.

## Predeclared comparisons, including regressions

The separate v2 development draft keeps the original 300-step scoring rules and
adds six **scripted development probes**, not unseen physics tests: two seeds
each for lateral contact interruption, forty-step object clamping, and a goal
crossing. Interventions occur at step 90 and are marked in raw trajectories.
The controller sees only the resulting observations. Task geometry is changed
by the developer harness, never by a controller or agent.

Each experiment runs four variants on all 21 episodes: full, without stabilized
tracking/reacquisition, without controlled repush, and without special correction.
The stabilization ablation disables two related enum fields; it is not an
isolated estimate of approach versus contact-reacquisition effects.

| Full strategy version | Nominal /5 | Mass /5 | Delay /5 | Contact /2 | Stall /2 | Crossing /2 | Total | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| First | 5 | 2 | 1 | 1 | 1 | 0 | 10/21 | 51.3974 |
| Early-response probe + segment crossing | 5 | 1 | 3 | 1 | 1 | 1 | 12/21 | 59.3720 |
| Position-first recovery + persistent waypoint + contact tracking | 4 | 2 | 3 | 0 | 1 | 0 | 10/21 | 51.9867 |

The latest full variant scores 51.9867 versus 45.4801 without stabilization, but
the changes **regress nominal/contact/crossing results**. The best recorded
variant is the second experiment **without repush**, 13/21 and 62.7846. Thus the
data do not establish that controlled repush is superior to reapproach.
No result is promoted; the latest code is not presented as the best candidate.
These 21-episode scores must not be compared directly with v1's 15-episode score.

The second experiment includes an actual overshoot → reposition → corrective
push → settled success (crossing seed 1); the first/second include actual
controlled-repush successes (stall seed 0). Contact-interruption success without
a retry is recorded separately from successful explicit recovery. The third
experiment preserves failures rather than hiding them behind final error.

All 252 episodes are eligible under the existing finite-state/action/time checks.
All three evidence bundles contain original trajectories, pre-run specifications,
source snapshots, reports, and recomputable gate results:
[first](evidence/strategy-v2/first/report.json),
[second](evidence/strategy-v2/response-probe/report.json),
[third](evidence/strategy-v2/position-contact/report.json).
No gain search or held-out tuning was performed; algorithm changes were informed
by these development observations.

## Why TrueForge is still gated

Before the first comparison, the v2 draft specified: 5/5 nominal, at least 2/5
mass and 3/5 delay, all episodes eligible, and at least one successful explicit
post-intervention retry in each probe family. **No measured full strategy passes
all checks.** The latest fails nominal, contact-recovery and crossing-recovery.
Activation was attempted and correctly refused without creating a v2 freeze.

The [gated v2 integration](TRUEFORGE_V2.md) is implemented: strict enum-only YAML,
independent protocol/freeze machinery, six MCP tools, isolated persistent budgets,
concurrency locking, immutable strategy versions, hash-checked evaluation and
promotion, and a guarded TrueForge launcher. A live developer MCP check discovers
six tools on port 8766 and reports `enabled: false`, with **6 evaluations,
12 trials, 4 saves unspent**. This is not a configured/running TrueForge v2 agent.

The full test suite passes **106 tests**. Raw evidence is independently re-scored;
deterministic tests cover diagnosis, skipped-sample crossing, strategy transitions,
waypoint bounds, infeasible IK, source locks, gate enforcement, budget persistence,
path/schema rejection, concurrency and promotion tampering. Original freeze
locks, skill/evidence bytes and v1 budget/held-out receipts remain unchanged.

The next bottleneck is reachable contact-side positioning and enough time to
complete recovery without losing nominal performance. Successful reapproach
after contact interruption must be established before activation. Only then
should TrueForge choose/revise these developer primitives through real tool
calls, followed by genuinely unseen-condition evaluation after finalization.
