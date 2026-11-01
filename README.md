# RealityShift

[![Tests](https://github.com/shivanginarayan/RealityShift/actions/workflows/tests.yml/badge.svg)](https://github.com/shivanginarayan/RealityShift/actions/workflows/tests.yml)

## Recorded adaptation result

The TrueForge/NVIDIA Nemotron agent generated v2–v4 and promoted v4 on fixed
development metrics: **5/15 → 6/15 successes**, score **35.24 → 41.83**.
On final unseen seeds, both skills succeeded **5/15** and v4 scored worse
(**34.70 versus 36.45**). Conventional random search also scored higher than the
agent on development (**44.62**). This is a measured development improvement
with a held-out regression, not robust generalization or real-hardware transfer.
See [results and limitations](docs/AGENT_RESULTS.md) and the recorded tool evidence.

**[Watch the 90-second TrueForge demonstration](demo/assets/realityshift_trueforge_demo.mp4)**:
nominal success, shifted failure, actual agent skill revision, paired improvement,
and the full development/held-out results. [Video provenance](docs/DEMO.md).
Current scope is the TrueForge challenge only; Shelled work is excluded.
[Submission evidence](docs/TRUEFORGE_EVIDENCE.md) | [Completion report](docs/COMPLETION_REPORT.md).
[Submission packet and final checklist](docs/SUBMISSION_PACKET.md).

**Developer-only v2 increment:** [bounded recovery and measured limitations](docs/RECOVERY_V2.md)
adds observation-based failure detection and retries in a separate opt-in controller.
It preserves v1 and has not been tested in a new TrueForge experiment. On existing
development cases, score improves to 37.35 but shifted-case successes remain zero.

[Increment 2 developer ablation](docs/RECOVERY_INCREMENT2.md) adds confirmed stalls
and bounded nominal-model tracking: 8/15 development successes, score 54.70, with
a nominal regression to 3/5. These opt-in strategies remain outside the active
TrueForge bridge and have no new agent or unseen-condition result.

Investigating skill adaptation across simulated changes in robotic pushing physics.
This project contains the simulator foundation and a nominal model-based pushing
controller, paired physics-shift experiments, and a recorded TrueForge/Nemotron
adaptation run.

## Setup

Run from this directory in an Anaconda Prompt:

```powershell
conda env create -f environment.yml
conda activate RealityShift
python -s -m simulation.smoke --seed 42
python -s -m pytest -q
```

If the environment already exists, activate it and install with
`python -s -m pip install -r requirements-lock.txt`. The `-s` flag excludes global
user packages from this project's Python commands.
`requirements-lock.txt` records the exact installed Python package versions from
the verified Windows setup and is the default Conda setup input. The broader
requirements.txt file is available for dependency development.

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

## Versioned skills and frozen development benchmark

The reference policy now reads `skills/initial.yaml`. The schema permits only
bounded numeric controller settings. Unknown fields, duplicate YAML keys,
non-finite numbers, boolean numeric values and excessive torque are rejected.
`control.skill_schema.save_candidate` saves versions 2 and above to
`skills/versions/vNNNN.yaml` and refuses to overwrite an existing version.

```powershell
python -s -m evaluation.benchmark
# After an agent has generated a validated candidate:
python -s -m evaluation.benchmark --skill skills/versions/v0002.yaml
```

Benchmark v1 uses the same 300-step horizon, 5 cm tolerance and final ten-step
settling rule, with seeds 0–4 in each of three scenarios (15 episodes). It checks
frozen source hashes before and during runs, snapshots the skill, and derives
metrics from raw observations and issued/applied actions. Candidate skill data
cannot set scoring thresholds, scenario definitions or benchmark seeds.

Initial skill result: **5/15 successes, 35.2412/100**, all episodes eligible under
the finite-value and torque checks. All nominal seeds succeed; all shifted seeds
fail. The refactor preserved exact issued actions and observations against the
prior experiment on all 15 episodes. Recorded results: `docs/BASELINE_V1.json`.
See `docs/EVALUATION.md` for scoring, promotion requirements and limitations.

## TrueForge integration

The local MCP bridge exposes six bounded tools for diagnostics, skill saving,
diffs, evaluation and promotion. TrueForge 0.182.0 has registered the connector
and discovered all six tools. A real developer MCP diagnostic trial completed;
the full test suite covers simulation, skill validation, scoring, bridge limits,
launcher preflight, replay and original-evidence verification. Source hashes for benchmark v1 are unchanged.

See `docs/TRUEFORGE.md` for startup commands and NVIDIA configuration. The agent now uses NVIDIA Nemotron through its hosted endpoint. It generated three
candidate skills and promoted v4 after a measured development improvement.
Held-out results regressed; see the results above. Implementation code was
developer-authored; candidate YAML was generated by the TrueForge agent. The
original diagnostic response hit the harness size limit; baseline and candidate
evaluation responses remained available. This limitation is preserved in the trace.

## Recorded video replay

Install `requirements-demo.txt`, then render a paired run:

```powershell
python -s -m pip install -r requirements-demo.txt
python -s -m demo.render_replay --left experiments/shifts/20261101T062357611693Z/nominal/seed0 --right experiments/shifts/20261101T062357611693Z/actuator_delay/seed0 --output experiments/demo/nominal_vs_delay.mp4
```

For a fresh checkout, first run `python -s -m simulation.compare` and substitute
its generated experiment directory. Input experiments are local artifacts and
are not included in Git. Both sides must use the same seed, controller and skill.

The renderer verifies trace hashes, simulator package versions, physics settings,
every replayed observation and applied action, and the independently scored
recorded outcome. It writes a synchronized MP4, final-frame PNG and JSON evidence
manifest with the video hash. Existing output videos are not overwritten.

Generated example: `experiments/demo/nominal_vs_delay.mp4`, 15 seconds at 20 fps.
Seed 0 ends at 0.0111 m nominal error versus 0.3415 m with delayed commands.
This demonstrates the failure under a shift; it does not show agent adaptation.

## Conventional random-search comparison

```powershell
python -s -m evaluation.baselines --sampler-seed 42
```

This evaluates v1 plus three randomly sampled skills under the unchanged frozen
benchmark: four full evaluations, matching the agent's full-evaluation allowance.
All samples are recorded before outcomes are observed. These developer-run
optimizer results are separate from agent candidates and never change promotion
state. See `docs/BASELINES.md` for sampling, selection and budget limitations.
Recorded best result: **6/15 successes, 44.6180/100**, versus initial **5/15,
35.2412/100**. This is the conventional baseline for the recorded TrueForge comparison;
it is not evidence of autonomous adaptation or held-out generalization.

## Automated checks

GitHub Actions runs on pushes, pull requests and manual dispatch using Windows
and Python 3.11. It installs the pinned simulator dependencies, checks dependency
consistency, verifies the frozen benchmark and runs all tests. It needs no model
API keys, running TrueForge service, graphical desktop or saved experiment files.
The workflow does not execute the paid model-driven adaptation loop.

## Final evaluation readiness

The held-out protocol is prepared and separately fingerprinted. It evaluates
one finalized candidate and the initial skill on 15 episodes each, using unseen
seeds with the same physics shift values and unchanged scoring rules. It requires
the final development skill hash and reserves access before running. The final comparison has now been executed once for frozen skill v4. See
`docs/HELDOUT.md` for the protocol and `docs/AGENT_RESULTS.md` for measured outcomes.

The real adaptation run now has a CLI launcher and paginated trace exporter.
After configuring the model and saved agent, use `python -s -m agent.run_adaptation`.
It prints the follow-up command for exporting session evidence and preserves
failed/incomplete statuses. The NVIDIA-backed session and tool calls are recorded in
`docs/evidence/nemotron/`. The earlier missing-provider preflight was also verified.

Environment reference: https://gymnasium.farama.org/environments/mujoco/pusher/

## Verify the original result without API calls

```powershell
python -s -m evaluation.verify_evidence
```

This re-scores 92 original saved trajectories in the published archive: 60
development episodes, 30 held-out episodes and two diagnostics (one developer
smoke check, one agent-requested trial). It checks hashes, saved skill values,
agent tool responses and the promotion gate. It starts no simulator or model
session. The original four-evaluation budget remains exhausted.
