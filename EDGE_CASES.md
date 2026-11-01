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
