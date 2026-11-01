# RealityShift submission packet

This is copy-ready draft text, not a submitted entry. Confirm the participant
portal's actual field labels and eligibility questions before submitting.

## Project fields

**Name:** RealityShift

**Track:** Hard problems

**Challenge:** Build a self-improving agent — TrueForge by TrueFoundry

**One sentence:** A TrueForge-managed agent revises a persistent robotic pushing
skill from experiment feedback, with frozen scoring and an auditable result.

**Who it is for:** Robotics and agent researchers investigating whether a model
can adapt an operational control skill when simulated dynamics change.

**What it does:** RealityShift runs a MuJoCo pushing controller under nominal,
increased-mass and delayed-actuation conditions. A restricted MCP bridge lets a
TrueForge/NVIDIA Nemotron agent evaluate the initial skill, request a diagnostic,
save versioned YAML revisions and evaluate them against an unchanged benchmark.
The agent generated v2–v4; v4 passed the development promotion gate.

**Measured result:** Initial v1 succeeded on 5/15 development episodes with score
35.2412. Agent v4 succeeded on 6/15 with score 41.8346. Both had zero ineligible
episodes under fixed finite-state, timing, completion and torque checks.
The higher-scoring conventional random-search baseline reached 44.6180.
On the first final unseen-seed test, both v1 and frozen v4 succeeded 5/15;
v4 scored worse, 34.6993 versus 36.4483. The development gain did not generalize.

**Genuine agent work:** TrueForge executed two actual model-driven turns in
session `01m6b09r6y75stas7g5nx86bna`. Candidate YAML came from its save tool;
the developer did not insert revised parameter values. Four full evaluations
were used including baseline, without resets. The original diagnostic response
hit the harness size limit, so full diagnostic telemetry was not received by the
model; baseline/candidate episode metrics were received. This limitation remains
visible in the public trace.

**What existed before:** No existing application code was in the newly created,
non-fork repository. The project reused installed tools/libraries and Gymnasium's
existing Pusher-v5/MuJoCo task. The simulation wrappers, controller, skill schema,
evaluator, bridge, launcher, evidence tooling and video composer were developed
for this project. Candidate skills were agent-generated. See the dependency
license inventory; no reinforcement-learning training or hardware validation is
claimed. Earlier Shelled plans were abandoned and are outside this submission.

**Improvement recap:** The first agent candidate underperformed. A developer
follow-up asked the same session to use its remaining evaluation budget without
providing parameter values. The agent generated two more candidates and promoted
v4 on measured development results. No further tuning followed the final
held-out regression. This is a technical iteration recap, not a claim of external
builder feedback or completed Trick or Feedback tries.

## Public links

- Repository: https://github.com/shivanginarayan/RealityShift
- Technical proof: https://github.com/shivanginarayan/RealityShift/blob/main/docs/TRUEFORGE_EVIDENCE.md
- Complete results: https://github.com/shivanginarayan/RealityShift/blob/main/docs/COMPLETION_REPORT.md
- Real tool trace: https://github.com/shivanginarayan/RealityShift/blob/main/docs/evidence/nemotron/session-tools.jsonl
- Saved skill: https://github.com/shivanginarayan/RealityShift/blob/main/skills/versions/v0004.yaml
- Demo page/download: https://github.com/shivanginarayan/RealityShift/blob/main/demo/assets/realityshift_trueforge_demo.mp4
- Direct video bytes: https://raw.githubusercontent.com/shivanginarayan/RealityShift/main/demo/assets/realityshift_trueforge_demo.mp4
- Reproducibility: https://github.com/shivanginarayan/RealityShift#verify-the-original-result-without-api-calls

The video is 90 seconds and public in the repository. The authenticated portal
has not been checked; if it requires a hosted-video service, upload the existing
MP4 unchanged and enter that public/unlisted URL. A GitHub file link is not
asserted to pass every possible portal URL validator.

## New-project proof

GitHub's public API reports creation at **2026-11-01 04:47:19 UTC**, public visibility
and `fork: false`. This is after the published **2026-10-30 23:00 UTC** opening.
See `submission-readiness.json` for the unauthenticated check, timestamp and file
links. This verifies the repository facts, not all participant eligibility.

## Final checklist

- Confirm registration/pact/account eligibility privately; never publish identity
  documents, credentials or API keys.
- Confirm your registered display name and final team membership in the portal.
- Confirm original-code licensing; dependency declarations are inventoried in
  `DEPENDENCY_LICENSES.md` but do not license the project's own code.
- Open/declare only the TrueForge challenge and attach its actual evidence.
- Add the accepted public proof-of-launch video URL and verify playback while
  signed out. Submit English text/captions.
- Review all fields, then perform the final submission in the participant app.
  A draft or Git push is not a submission. Judge confirmation remains pending.
- Keep public links working through **November 19, 2026**.

The official close is **November 9, 2026 at 02:59 UTC**, which is **November 8 at
6:59 p.m. Pacific Standard Time** in Los Angeles. Recheck for announced changes
before submitting. Source: [official rules, updated October 30](https://strangerbuilds.com/rules).
