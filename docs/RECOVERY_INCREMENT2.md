# Recovery increment 2: confirmed stalls and bounded tracking

Developer-authored, opt-in strategies in `control/settled_recovery.py`. No
TrueForge session, agent-authored strategy, gain search or held-out simulation
occurred. The original v1 controller and measured increment 1 controller remain
unchanged; neither new strategy is made the default or promoted.

**Stall confirmation:** require eight consecutive stall indications before
retrying. Lost contact and overshoot keep their existing debounce/criteria.
The archived nominal transient at steps 71–74 no longer triggers recovery.

**Tracking strategy:** use the same nominal IK targets, but replace the direct
PD torque law with nominal inverse dynamics. Desired joint speed is capped at
0.8 rad/s and requested acceleration at 2 rad/s², with a fixed 0.4 s velocity
response. The nominal inertia, bias and passive joint forces translate this
request into bounded torques. Actual acceleration is not guaranteed under
contact/delay. Only observed robot joints enter this independent model; shifted
parameters, applied actions and contact/constraint forces are excluded. The
strategy uses longer bounded approach/recovery deadlines (100/65/180 steps)
and still allows at most two retries. The v1 PD gains and smoothing law are
replaced rather than tuned; torque bounds and geometric skill fields remain.

## First development comparison

Existing seeds 0–4, the same three development scenarios, 300 steps and unchanged
scoring. Two new strategies ran 30 episodes; the 30 original v1/increment 1
baseline episodes were reused after offline verification. No test cases were
selected after seeing outcomes; no follow-up parameter search was performed.

| Controller | Nominal | Mass | Delay | Total | Score |
| --- | --- | --- | --- | --- | --- |
| Original v1 | 5/5 | 0/5 | 0/5 | 5/15 | 35.2412 |
| Increment 1 recovery | 5/5 | 0/5 | 0/5 | 5/15 | 37.3526 |
| Stall confirmation only | 5/5 | 0/5 | 0/5 | 5/15 | 37.5819 |
| Bounded tracking + confirmation + longer deadlines | 3/5 | 2/5 | 3/5 | 8/15 | 54.6967 |

All new episodes pass existing completion/time/finite-state/torque checks.
Tracking strategy mean final error is **0.11958 m**, versus **0.18363 m** for
increment 1. Mean issued squared torque falls from 2.94916 to 0.02212; this is a
command statistic, not measured energy or a physical-robot result.

The main tradeoff is explicit: nominal success regresses to 3/5. One nominal run
ends 6.94 cm away; another enters tolerance too late to satisfy final-ten-step
settling. Three mass runs exhaust retries while approaching moving/unreachable
targets. All eight successful tracking runs use **zero retries**. Consequently,
the gain establishes better tracking on known shifted cases, **not successful
reapproach recovery** or unseen-condition generalization. The bundled tracking
law and longer deadlines were not separately ablated; their individual effects
remain uncertain.

## Verification and next work

The full suite passes **75 tests**, including confirmation/reset, unchanged
contact/overshoot behavior, archived transient replay, retry exhaustion,
deterministic bounded commands, live-state isolation, evidence newline
portability and independent raw-trajectory re-scoring. Original frozen
protocols, skills, evidence and experiment budgets remain intact.

```powershell
python -s -m evaluation.verify_settled
python -s -m pytest -q
# Optional separate developer comparison, refusing existing outputs:
python -s -m evaluation.settled_comparison --output experiments/recovery-v2/new-ablation
```

[Report](evidence/recovery-increment2/report.json),
[pre-run manifest](evidence/recovery-increment2/manifest.json),
[archive index](evidence/recovery-increment2/archive.json),
[30 trajectories and measured sources](evidence/recovery-increment2/trajectories.zip).

Next work should isolate tracking from recovery deadlines, test reapproach with
predeclared controlled contact interruptions, and address the nominal regression.
Future strategy selection must use observed behavior, not known scenario IDs.
Only after that should a separately versioned TrueForge strategy schema/budget
and reserved unseen-condition protocol be enabled. The original v1 experiment
and its one-shot held-out evidence remain closed.
