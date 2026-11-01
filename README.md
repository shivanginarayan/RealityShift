# RealityShift

Investigating skill adaptation across simulated changes in robotic pushing physics.
This project contains the simulator foundation and a nominal model-based pushing
controller, plus paired nominal and shifted-physics experiments. Autonomous
adaptation is still pending.

## Setup

Run from this directory in an Anaconda Prompt:

```powershell
conda env create -f environment.yml
conda activate RealityShift
python -s -m simulation.smoke --seed 42
python -s -m pytest -q
```

If the environment already exists, activate it and install with
`python -s -m pip install -r requirements.txt`. The `-s` flag excludes global
user packages from this project's Python commands.
`requirements-lock.txt` records the exact installed Python package versions from
the verified Windows setup; use it instead of requirements.txt for that setup.

The smoke command runs one complete Pusher-v5 episode with seeded random actions.
It writes `trajectory.jsonl` and `summary.json` under `experiments/smoke/seed42/`.
The trace records observations, actions, simulation times, rewards and episode
boundaries. The summary includes package versions and a trajectory SHA-256 hash.
Outputs are local generated artifacts and are ignored by Git.

This smoke command checks installation and repeatability, not task success.

## Nominal pushing controller

```powershell
python -s -m simulation.nominal --seeds 0 1 2 3 4 5 6 7 8 9 42
```

The controller approaches above and behind the object, lowers the gripper, then
pushes toward the goal using inverse kinematics and bounded joint feedback.
Inverse kinematics uses a separate MuJoCo data instance; it never teleports the
live robot or object. Actions stay within the environment's torque limits.

This nominal development task uses **300 steps (15 simulated seconds)**, extending
Pusher's default 100-step horizon. Success means planar object-to-goal distance
stays at or below **5 cm for the final ten steps**. Planar distance is intentional:
the object center and goal marker have different fixed vertical coordinates.
This is a development acceptance check, not the final adaptation scorer.

Verified on the installed Windows environment: **11/11 successes** for seeds 0–9
and 42, with final planar errors from 0.0047 to 0.0417 m. These are development
seeds, including calibration seeds, and do not establish held-out generalization.
Traces, controller hashes, package versions, per-seed summaries and the combined
`report.json` are saved under `experiments/nominal/`. Re-running the same output
directory overwrites those artifacts; use `--output` to preserve a separate run.

## Physics shifts

```powershell
python -s -m simulation.compare
```

This runs seeds 0–9 and 42 in three scenarios with the same controller, horizon,
and success criteria. Each invocation writes a new timestamped directory under
`experiments/shifts/`. A manifest records source hashes and settings before runs;
per-episode JSONL includes issued and applied commands. An existing explicit
`--output` directory is rejected to preserve prior comparison artifacts.

Recorded development run `20261101T062357611693Z`:

| Scenario | Successes | Mean final planar error |
| --- | --- | --- |
| Nominal | 11/11 | 0.0164 m |
| High object mass | 0/11 | 0.6002 m |
| Actuator delay | 0/11 | 0.2518 m |

The mass probe multiplies stock object mass and inertia by 10,000; the stock
object is exceptionally light. This is an explicit simulated stress condition,
not a claim of a realistic payload distribution. The delay is four control steps
(0.20 s), with zero torque during queue warm-up. Reset clears queued commands.
The controller receives an independent nominal model and observations, rather
than the shifted simulator model. Physics manifests are developer artifacts and
must not be forwarded to a future adaptation agent.

Friction shifts are deferred: stock Pusher has `condim=1` frictionless contacts
and zero gravity. Changing friction coefficients alone would not demonstrate the
intended surface-friction shift. A contact-model redesign would need a separately
calibrated nominal baseline. See MuJoCo's contact documentation:
https://mujoco.readthedocs.io/en/stable/computation/index.html

Next: freeze the adaptation evaluator and implement validated versioned control
skills. All current code was developer-implemented; Shelled PR provenance and
TrueForge integration remain pending.

Environment reference: https://gymnasium.farama.org/environments/mujoco/pusher/
