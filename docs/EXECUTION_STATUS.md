# Execution priorities status

| Priority | Status | Evidence |
| --- | --- | --- |
| Configure TrueForge model and saved agent | Completed with NVIDIA Nemotron | `TRUEFORGE.md`; recorded session metadata |
| Real autonomous skill revision and evaluation | Completed; developer follow-up used remaining budget | `AGENT_RESULTS.md`; `evidence/nemotron/session-tools.jsonl` |
| Real substantive Shelled PRs | Blocked on signed-in workspace/tool access | `SHELLED_TASKS.md`; no PR claims made |
| Finalize candidate then perform held-out evaluation | Completed once; original results retained | `evidence/nemotron/heldout-manifest.json` and `heldout-report.json` |
| Demonstrate nominal success, shift failure, actual revision, measured improvement | Completed as an 88-second recorded video | `DEMO.md`; `demo/assets/realityshift_demo.mp4` |

The baseline score was 35.2412; the agent's promoted v4 scored 41.8346, with
development success increasing from 5/15 to 6/15. The initial failed candidate and
all subsequent outcomes are preserved. No evaluator or experiment budget reset
was used to obtain the result. Random search scored higher, and held-out v4
regressed. Those facts are visible in the demo and README.

The four-evaluation adaptation experiment is closed. Do not tune on the final
results. Further development can improve diagnostics, artifact handling and demo
usability while preserving this experiment's evidence and limits. Genuine
Shelled PR work is the remaining execution priority; service access and a
no-additional-cost workflow must be established before starting it.
