# TrueForge integration completion report

## Existing implementation preserved

MuJoCo/Gymnasium pushing, nominal feedback control, mass/delay wrappers,
deterministic traces, strict YAML skills, frozen scoring, MCP bridge, local
TrueForge launcher, persistent budgets, versioned candidates, random-search
comparison, one-time final evaluation and replay/video infrastructure already
existed. The actual NVIDIA-backed experiment had completed before this audit.
It was not repeated or relabeled as a new run.

## Audit changes

Published secret-free agent/model configuration, agent hypotheses, diagnostic
results, bridge audit, an explicit v1/v4 diff and 92 original raw trajectories.
Added an offline evidence verifier and tamper checks. Made the default Conda
setup use the existing exact dependency lock. Corrected stale OpenAI,
held-out and Shelled documentation. Added a fail-fast launcher guard for an
exhausted local evaluation budget.

Found and fixed a real bridge issue: the original diagnostic response exceeded
TrueForge's 24,000-character limit. Future displayed telemetry is sampled to 21
states, rounded to six decimals and bounded below 16,000 pretty-printed
characters. Full raw trajectories and computed metrics are unchanged. Historical
evidence retains the original size-limit notice; it was not retroactively fixed.

Created a TrueForge-only 90-second demo and preserved the previous 88-second demo
and all prior experiment evidence. No frozen controller, simulator, schema,
scorer, specification or lock was changed. No new model/adaptation/final run was
started and no budget was reset during the audit.

## Actual execution and results

Provider: NVIDIA hosted Nemotron. Session `01m6b09r6y75stas7g5nx86bna` completed two
real model-driven turns. The agent generated v2, v3 and v4 through the save tool.
V2/v3 failed the gate; v4 was promoted through the existing gate. Developer code,
random-search candidates and TrueForge YAML authorship are distinguished.

| Metric | Development v1 | Development v4 | Held-out v1 | Held-out v4 |
| --- | --- | --- | --- | --- |
| Successful episodes | 5/15 | 6/15 | 5/15 | 5/15 |
| Success rate | 33.3333% | 40.0000% | 33.3333% | 33.3333% |
| Fixed score | 35.2411556947 | 41.8345951807 | 36.4482616805 | 34.6992814479 |
| Mean final XY error, m | 0.3085628483 | 0.2446857608 | 0.2299571030 | 0.3049609690 |
| Mean issued squared torque | 3.0025904437 | 2.6600928839 | 2.8379475194 | 2.6765368776 |
| Ineligible episodes | 0 | 0 | 0 | 0 |

Effort is the mean squared issued joint torque over joints and timesteps, not
mechanical energy. Zero ineligible episodes refers to the fixed finite-value,
completion, timestamp and torque checks; it does not establish collision or
physical robot safety.

**Development improvement verified. Held-out generalization gate failed.** The
first held-out outcomes remain intact. Conventional random search scored
44.6180333551 with 6/15 successes on development, exceeding agent v4. It was not
evaluated on the final suite and no held-out comparison to it is claimed.

## Validation and evidence locations

The final local test result is recorded in `audit-validation.json` alongside this
report. The tests cover simulation, skills, scorer invariance, bridge boundaries,
response size, model-run preflight, replay and evidence tampering. Original raw
evidence re-scoring confirms all 92 saved episodes without simulation/API calls.
See TRUEFORGE_EVIDENCE.md for the full file/claim map.

Video: `demo/assets/realityshift_trueforge_demo.mp4` and its JSON provenance.
Source/evidence: `docs/evidence/nemotron/`; saved skills: `skills/versions/`.
Original private runtime/session data is retained under ignored `.runtime/`.

## Remaining submission work

The technical development-improvement result is present. Remaining external
steps are confirming current organizer/challenge eligibility and deadline,
completing the participant-portal fields, uploading/linking the demo as required,
and verifying all submitted public links from a signed-out browser. This audit
does not claim organizer acceptance, prize eligibility, or a generalization win.
Shelled is explicitly excluded. No additional spending is required by this audit.
