# Development benchmark version 1

This benchmark is fixed before attempting agent-authored improvements. It uses
five existing development seeds (0–4) in nominal, high-mass and four-step-delay
scenarios. These seeds have been observed during development and are not held out.
The final unseen-seed evaluation has now run once on frozen agent skill v4;
it regressed and is reported in AGENT_RESULTS.md.

## Fixed rules

`evaluation/spec.json` specifies 300 steps, 0.05 seconds per control step, 0.05 m
planar goal tolerance, ten final settling steps, and a 2.0 absolute torque bound.
The independent scorer recomputes planar distance from observation coordinates;
it ignores environment reward and any trajectory field claiming a distance.
Episodes with incomplete trajectories, invalid times, non-finite observations,
or invalid issued/applied torques are ineligible. Any ineligible episode makes
the complete suite ineligible for promotion. These are computational guards,
not a claim of physical robot safety or collision-force validation.

For an eligible episode:

`score = 70 * success + 20 * (1 - clipped_final_error / 0.5) + 10 * (1 - settled_time_fraction)`

Here `clipped_final_error / 0.5` means `min(final_error_m / 0.5, 1)`. Success
requires all final ten distances to be at or below tolerance. Settling time is
the start of the final continuously successful suffix, normalized by 300 steps.
Failed episodes get a normalized settling time of one. The suite score is the
mean episode score, or zero if any episode is ineligible.

Promotion requires eligibility, a strictly higher suite score, and a strictly
better lexicographic ranking: success rate first, then lower mean final error,
then lower mean squared issued torque. A lower success rate cannot be rescued
by the scalar score. The current `can_promote` function evaluates this gate;
the agent bridge now enforces this gate when given two completed evaluation IDs.
A real TrueForge/Nemotron v4 candidate passed the development gate and was
promoted. Its final unseen-seed results regressed; see AGENT_RESULTS.md.

## Freeze and skill boundaries

`evaluation/frozen.json` fingerprints evaluator code, specification, simulator,
scenario definitions, controller implementation, skill validator and initial
skill. Source hashing normalizes UTF-8 BOMs and line endings for Windows Git
checkouts. Candidate YAML files are data and are not in the source freeze.
Evaluator changes require an explicitly new benchmark version and a re-recorded
baseline; do not silently regenerate the lock to make a candidate pass.

Each benchmark invocation creates a fresh output directory, saves a validated
skill snapshot, and records benchmark hashes before execution. Raw simulator
artifacts include developer-only physics manifests and applied torques; a future
agent tool must filter those artifacts to avoid revealing hidden shift settings.
The controller receives a separate nominal kinematic model, not the shifted model.

Hash verification detects accidental or unauthorized source changes but is not
an operating-system sandbox. A process with repository write access could alter
the lock or evaluator. The future agent must receive restricted tools rather
than unrestricted shell or repository access.

## Baseline evidence

`docs/BASELINE_V1.json` is copied from the actual run at
`experiments/benchmark/20261101T062909759511Z/report.json`. Raw trajectories,
the skill snapshot and pre-run manifest remain in that local generated directory.
The tracked report allows review; reproduce raw artifacts with:

```powershell
python -s -m evaluation.benchmark
python -s -m pytest -q
```

Observed: 5/15 successes, score 35.24115569470959, all episodes eligible.
Initial-skill actions and observations matched the previous recorded controller
experiment exactly on all 15 episodes. Full test suite: 25 passed. This is a
developer baseline, not TrueForge execution or evidence of self-improvement.

Original scores can now be recomputed from the published raw trajectory archive
with `python -s -m evaluation.verify_evidence`, without a model or simulator call.
The verifier is outside the frozen scorer and does not alter experiment rules.
