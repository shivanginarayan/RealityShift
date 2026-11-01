# Observed development cases

## Nominal control calibration

The initial position-only controller contacted the object at inconsistent angles
and sometimes increased target error. Adding gripper orientation alignment and
an above-object approach improved contact. An approach offset of 0.14 m stalled
seed 0; reducing that offset to 0.09 m allowed it to complete. These were manual
developer calibration trials, not agent-authored improvements. Early calibration
console output was not retained as benchmark evidence.

The controller did not reliably complete within the stock 100-step episode.
The nominal development task therefore explicitly uses 300 steps. Comparisons
must use the same horizon for all candidate controllers.

## Recorded nominal verification

Reproduce from the repository root:

```powershell
python -s -m simulation.nominal --seeds 0 1 2 3 4 5 6 7 8 9 42
python -s -m pytest -q
```

Observed: 11 of 11 episodes met the final-ten-step 5 cm planar-distance criterion.
Maximum final distance was 0.0417 m (seed 4). All three tests passed, including a
check that controller planning leaves live joint positions unchanged. The runner
checks finite state/reward and action bounds at every step. Torque saturation at
2.0 occurs; legal torque bounds alone do not establish a broader safety guarantee.

Recorded artifacts: `experiments/nominal/report.json` and per-seed JSONL traces.
No shifted physics, adversarial robustness, or held-out performance is established
by this verification. Future failures should be added with saved reproduction
artifacts and exact configurations.

## Recorded physics-shift failures

Command: `python -s -m simulation.compare`.

Artifacts: `experiments/shifts/20261101T062357611693Z/manifest.json`, `report.json`,
and per-scenario, per-seed trajectories. The manifest stores source hashes and
settings from before execution. These are local generated artifacts, not tracked
Git files or sponsor provenance.

| Condition | Observed successes | Mean final XY error |
| --- | --- | --- |
| Nominal | 11/11 | 0.0164 m |
| Object mass and inertia multiplied by 10,000 | 0/11 | 0.6002 m |
| Four-step command delay (200 ms) | 0/11 | 0.2518 m |

All runs used seeds 0–9 and 42, 300 steps, and the same final-ten-step 5 cm
criterion. These shifts degrade performance without changing the controller or
success rule. No improved policy has been evaluated. The aggregate mass result
does not establish a specific failure mechanism; inspect trajectories before
claiming insufficient force or overshoot.

Repeated delay runs with seed 42 produced identical trajectory hashes. Automated
checks confirm reset empties delayed commands, zero delay passes commands through,
negative/fractional/boolean/excessive delays are rejected, and malformed,
non-finite, or out-of-bounds actions are rejected before simulation. Mass changes
scale inertia too, update MuJoCo derived constants, and preserve seeded initial
observations. Full suite: 11 tests passed.

Friction coefficients are deliberately not presented as a working shift: stock
Pusher's `condim=1` contact model is frictionless. Implementing surface friction
requires redesign and recalibration rather than relabeling coefficient changes.

## Skill and evaluator validation

Reproduce with `python -s -m pytest -q` (25 tests passed). Observed checks:

- Duplicate skill keys, unknown fields, boolean numeric fields, NaN values,
  excessive torque, invalid smoothing and modified scorer fields are rejected.
- Candidate v1 is rejected; candidate v2 is saved to its versioned location;
  saving the same version again raises rather than overwriting it.
- Changing claimed rewards or error fields does not alter independently computed
  scores. A late goal-distance excursion fails the settling criterion.
- Incomplete episodes, NaN observations and excessive applied torque are
  ineligible. Unsafe or equally performing candidates fail the promotion gate.
- A modified frozen source file is detected before evaluation.

Benchmark v1 initial skill: 5/15 successes, score 35.2412, all episodes eligible.
Exact observation/action comparisons against the prior fixed controller matched
for all 15 paired episodes. No agent-authored candidate has been evaluated yet.

## Agent bridge checks

The suite now has 31 passing tests. Additional checks reject path-like skill
identifiers, unknown cases, non-development seeds, candidate overwrites and
evaluation IDs that never completed. Trial budgets survive bridge restarts.
A real diagnostic test confirms returned telemetry excludes physics manifests,
mass scales, inserted delay values and applied actions. Promotion tests use
synthetic fixtures to verify acceptance persistence and reject altered report
evidence; they do not establish a measured candidate improvement.

TrueForge initially rejected the loopback connector URL. Its supported
`OUTBOUND_URL_ALLOWED_HOSTS` exception for `127.0.0.1` allowed registration and
discovery of all six tools. A direct MCP protocol check executed one real trial.
No configured model/provider or TrueForge model-driven run exists yet.

## Replay verification

Generated `experiments/demo/nominal_vs_delay.mp4` from the recorded seed-0 nominal
and actuator-delay runs. All 300 observations and applied actions on each side
were reproduced before accepting the video. At 20 fps this gives 15 synchronized
seconds; annotations identify the fixed controller, seed, simulated time, target
error and recorded outcome. The final frame was visually inspected.

Replay tests confirm that an edited trace fails its hash check and that changing
only the claimed outcome cannot override the independently scored trajectory.
A complete non-rendering replay reproduces recorded states without running a
controller. Full test suite: 34 passed. No benchmark source or skill changed.

## Random-search comparison

Reproduce: `python -s -m evaluation.baselines --sampler-seed 42`.
Recorded run: `experiments/random_search/20261101T070658694676Z/`.
Initial skill succeeded 5/15 (35.2412); random candidates succeeded 3/15
(24.8116), 6/15 (44.6180), and 0/15 (7.9082). The second sampled candidate
passed selection; it is a developer optimizer output, not an agent revision.
All three samples were saved before evaluation. No held-out outcomes were used.

New tests confirm reproducible valid sampling, an exact four-evaluation budget,
and rejection of scalar-score improvements that reduce task success. Selection
also rejects a candidate with equal success but worse final error, even if its
scalar score is higher. These selection edge checks use synthetic fixtures.
Full suite: 36 tests passed. Agent budgets and active skill state were untouched.

## Held-out protocol readiness

Three additional tests validate separate seed sets, rejection of mismatched final
skill hashes before reservation, pairing of thirty synthetic episodes, and
refusal of repeated final access. The synthetic runner does not execute held-out
simulation or provide actual held-out outcomes. Initial and final skills use the
same scoring rules, scenarios and seeds within each paired comparison. The final
protocol and runner are separately fingerprinted. Real held-out evaluation remains
unexecuted until the agent's candidate is finalized.
