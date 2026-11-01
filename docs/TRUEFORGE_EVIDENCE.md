# TrueForge evidence summary

The recorded experiment supports a narrow claim: a real TrueForge-managed
Nemotron agent wrote persistent numeric control revisions, and its later v4
evaluation improved the unchanged development benchmark. It does not support
generalization to held-out seeds, superiority to random search, or physical-robot
transfer. Organizer eligibility and submission acceptance are not established
by this technical evidence.

## Evidence map

| Technical requirement | Recorded evidence |
| --- | --- |
| Actual TrueForge execution | Session `01m6b09r6y75stas7g5nx86bna`; two completed turns in `evidence/nemotron/summary.json` |
| Real configured model | `agent-configuration.json`, `model-configuration.json`; credentials omitted |
| Run 1 | `initial-development.json`: 5/15, 35.24115569470959 |
| Agent-authored hypotheses and YAML | `agent-hypotheses.json`, `session-tools.jsonl`, `skills/versions/v0002.yaml` through `v0004.yaml` |
| Diagnostic execution | `diagnostic-results.json`, archived full trajectories, actual `run_trial` tool call |
| Diagnostic observation limitation | Original tool response is the harness's size-limit notice; do not claim full telemetry reached the agent |
| Persistent revision | Saved v4 YAML and `skill-v1-v4.diff` |
| Later evaluated improvement | `v0004-development.json`: 6/15, 41.83459518067389 |
| Verified promotion | `promote_skill` call/response in `session-tools.jsonl`; `promotion_decision` in `bridge-audit.jsonl` |
| Fixed independent scoring | `evaluation/frozen.json`, unchanged spec/scorer; all original episodes re-scored offline |
| First final outcomes | `heldout-report.json`, `heldout-manifest.json`; 5/15 both, v4 lower score |
| Visual demonstration | `demo/assets/realityshift_trueforge_demo.mp4`, with video/scene hashes in its JSON manifest |

All filenames above, unless prefixed otherwise, are under
`docs/evidence/nemotron/`. All three failed/improved candidate evaluations remain
published. The developer supplied a follow-up asking the same session to use its
remaining budget, but did not supply revised parameter values. Four full
evaluations were used, including baseline; no reset occurred. One diagnostic
was agent-requested and one was an earlier developer connection check.

## Independent verification without model access

```powershell
conda activate RealityShift
python -s -m evaluation.verify_evidence
python -s -m pytest -q
```

The published 7.3 MB `trajectories.zip` holds the exact original bytes of 92
episodes: sixty development, thirty final and two diagnostics. The verifier
checks archive/trace/report/skill hashes, re-scores raw observations and issued
actions using the frozen scorer, recomputes suite aggregates, matches actual
TrueForge evaluation responses, and verifies the promotion gate. It extracts no
archive paths, invokes no simulator, starts no model session and changes no
experiment budgets. `trace-archive.json` provides its file/hash manifest.

Hashes establish consistency, not an independent service signature. The original
TrueForge SQLite database and complete local event exports are preserved locally
for inspection; credentials/databases are not published. The public event export
retains every relevant tool call and response, including the diagnostic error,
while omitting model prose, private reasoning content and user prompt bodies.

## Limitations relevant to judging

- Revisions adjust existing numeric controls; no new recovery rule was written.
- The attempted diagnostic result was too large for the harness, so its full
  telemetry was not available to the agent. Baseline/candidate episode metrics
  were delivered. A later bridge-only response-size fix is documented separately.
- Development gain was 6.5934394859643 score points and one additional success.
  Random search scored 44.6180, above the agent's 41.8346.
- Held-out improvement failed: success stayed 5/15 and score fell from 36.4483
  to 34.6993. Final outcomes were not used for subsequent tuning.
- Only simulated mass/delay shifts and unseen seeds were evaluated. Friction
  shifts, unseen shift ranges and physical hardware were not validated.
- Agent access is restricted by tool design; hash checks are not an OS sandbox.

Shelled is excluded by the current user instructions. Earlier Shelled plans are
historical context and are not submission requirements or evidence claims here.
