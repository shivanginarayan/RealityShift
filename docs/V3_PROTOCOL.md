# V3: actuator-delay strategy adaptation

V1 and v2 already contain frozen experiments. The new task therefore uses v3,
with separate files, source lock, saved agent, MCP port and persistent budgets.
It does not reset or replace an earlier experiment.

## Conditions fixed before selection

| Set | Starting seeds | Delays | Delay starts | Episodes per policy |
| --- | --- | --- | --- | --- |
| Development | 0, 1, 2 | 0, 2, 4, 6 command steps | Start; 3.0 s for nonzero delays | 21 |
| Validation | 200, 201, 202 | 0, 2, 4, 6 command steps | Start; 3.0 s for nonzero delays | 21 |
| Final held-out | 1000–1004 | 0, 3, 5 command steps | Start; 4.5 s for nonzero delays | 25 |

One command step is 50 ms. Each seed includes one nominal task and every nonzero
delay/onset pairing. Final nonzero delays and the 4.5-second onset are absent from
development and validation. The previous held-out seeds 100–104 are not reused.
The same Gymnasium initial-position distribution and unchanged goal are used.

`simulation/delay_shift.py` preserves the actual earlier command history when
delay begins mid-task. It does not replace the history with artificial zero
commands at the change. A deterministic test establishes exact equivalence to
the previous four-step constant-delay environment. Delay, start time, seed,
applied command and scoring metadata never enter the controller or agent tools.

The horizon remains 300 steps/15 seconds, torque stays within ±2 and success
requires the final ten object-to-goal distances to be within 5 cm. No scenario
was made easier by moving goals, shortening delay or relaxing scoring.

## Strategy and agent boundary

`control/adaptation_schema.py` accepts a 4 KiB tagged YAML policy:

- Original controller: only `controller: original`.
- Recovery controller: six enum choices for approach, stall handling, overshoot
  correction, reacquisition, progress-gated tracking memory and pose-holding
  braking. No gain, code, file, condition or scoring parameters are accepted.

The new response-aware adaptive primitive latches stabilized tracking after
observed response deterioration or recovery entry. This repairs an initial
response preference that could otherwise keep returning to direct pushing.
All primitives are developer-authored. Actual saved choices and promotion tool
calls establish the agent's contribution; controller code is not agent-authored.

The separate TrueForge connector is `realityshift-adaptation-v3` at loopback
port 8767. Only six experiment tools are exposed. No sandbox/shell, web,
subagents, extra instruction packs or final-test endpoint are available. It uses
the existing NVIDIA alias `nvidia/nemotron-lightning`, with no paid fallback.

The bridge enforces a full initial validation evaluation before revisions.
Repeated baseline requests return the same completed evaluation without another
simulation or charge against the budget. Diagnostic trials accept only opaque
development IDs. Tool outputs exclude simulator condition labels and parameters.
The source lock and loaded-source guard prevent live evaluator changes.

## Comparisons, budgets and selection

The agent has at most six full validation evaluations including original,
twelve development trials and four immutable saves. A separate conventional
search has six full validation evaluations: original, a predeclared developer
anchor and four enum samples drawn with seed 20261102. Its choices are stored
in the protocol before validation outcomes exist. Search results are not fed
to the agent. The agent's optional diagnostic trials are reported separately;
equal validation caps do not imply identical total information or compute.

Promotion requires independently measured strict aggregate improvement **and
preservation of every original successful validation condition**. Trial IDs,
partial subsets and agent self-report cannot substitute for full evaluation IDs.
Failed evaluations consume their reserved budget. Existing directories and
reservations are not overwritten; crash locks fail closed.

The final comparison contains original, the fixed developer anchor, the best
eligible conventional policy and the actually promoted agent policy. Identical
policies can coincide; they must not be described as independent discoveries.
All canonical policies are reserved and hashed before any final outcome is
visible. A one-shot final reservation disables further agent mutations.

## Independent evidence and uncertainty

Raw observations, issued/applied commands, effective joint references, strategy
events, tracking memory, braking state and independent scores are preserved.
The effective reference logs the latched joint pose during braking, avoiding
the older marker-IK telemetry ambiguity. Public agent event projections remove
private model reasoning recursively while retaining actual tool calls, tool
responses, hypotheses, IDs, saved YAML and export-receipt hashes.

Success rate, final error, mean squared torque (an effort proxy, not energy),
retry entries, brake activations and failure categories are reported. Wilson
success intervals are descriptive: conditions share starting seeds. Paired
bootstrap differences resample whole seed clusters, not individual correlated
episodes. Validation has only three seed clusters and final evaluation five;
uncertainty and transfer claims must reflect those small samples.

The final split is protected by workflow and the agent tool boundary, not by
cryptographic secrecy from a developer with filesystem access. No final outcomes
are opened until policies are frozen. Once opened, they remain the first results;
they cannot be used for tuning and still called unseen.

This is a simulator research prototype motivated by manipulation and assistive
robots facing unfamiliar loads or degraded actuator response. It has no physical
hardware, clinical validation or authorization for unsupervised assistive care.
