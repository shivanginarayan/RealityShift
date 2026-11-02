# Progress-aware recovery increment

This developer experiment extends the frozen 15/21 controller without changing
v1, frozen v2, TrueForge instructions or any saved agent result. No model calls
or held-out evaluations are part of this comparison.

The remaining v2 failures suggest two distinct targets. Delay seeds 0 and 3
continue making progress without triggering stall recovery, but finish at
68.6 mm and 51.9 mm respectively, outside the 50 mm settling threshold. Their
median marker-to-command error during pushing is about 14.7 mm. Mass seeds
0, 2 and 4 get near the goal, overshoot, and fail subsequent recovery. Crossing
seed 0 exhausts its local contact planner. These are observed failure patterns,
not identification of unknown dynamics.

The delayed failures still gain 32.28 mm and 32.37 mm during the final 24 steps;
classifying those intervals as stalls would be misleading. The failed mass runs
enter their first hold at observed object speeds of approximately 0.731, 0.392
and 0.526 m/s, respectively (four-sample displacement divided by elapsed time).

`control/progress_recovery.py` adds two independently removable mechanisms:

- **Bounded tracking memory:** accumulate observed forward tracking error only
  during stabilized contact pushing. Limit each update to 2 mm and accumulated
  displacement to 30 mm. Reset on phase changes, recovery entry and object jumps;
  do not integrate during free-space approach, braking or direct pushing.
  The revised version also requires productive pushing over the existing
  24-observation/8 mm progress window before accumulating compensation.
- **Observed-motion braking:** stop commanding forward motion when recent object
  velocity predicts entering the goal corridor soon. Apply bounded nominal joint
  deceleration, without hidden mass, actuator delay, contact forces or injected
  intervention labels. Release after twelve samples if settling has not occurred.
  The revised brake holds the observed joint pose with nominal bias compensation
  instead of only damping joint velocity, which allowed load-induced drift.

These bounds define a new controller mechanism; no numeric-gain search is run.
The predictive corridor is a fixed heuristic, not a guarantee of stopping distance.
During braking, the frozen runner's `nominal_ik_error` and
`joint_reference_error_rms` still describe the inherited marker-IK calculation.
They are not tracking residuals for the separately latched joint-pose brake.
Raw observations and issued/applied actions remain the actual simulation history.

`evaluation/progress_comparison.py` runs baseline, full, without tracking memory
and without braking on the same 21 development episodes. It calls the unchanged
v2 episode harness with an explicit local controller substitution for the three
developer variants. The actual v2 MCP service continues to use its frozen class.
Every rerun baseline episode must exactly reproduce the archived score, final
error, effort and success before a candidate is interpreted.

The acceptance rule is declared before simulation: preserve **every** baseline
successful episode, increase total successes, remain eligible and lose no
successful explicit post-intervention recovery. Aggregate score alone cannot
accept a regressing candidate. All outcomes, including failed attempts, are kept
with measured source snapshots and can be re-scored without simulation.

Unit tests check tracking bounds/reset/phase gating, observed-motion braking and
release, rejection of invalid observations, and exact equivalence to frozen v2
when both new features are disabled. The equivalence test replays all 300 actual
observations from a successful contact-recovery episode.

## Preserved first attempt

The first 84-episode comparison reached 16/21 (74.3786) with both mechanisms,
15/21 (71.1639) without tracking memory and 16/21 (73.8545) without braking.
The full variant recovered mass seeds 2/4 and delay seeds 0/3, but lost nominal
seed 2, delay seed 2 and contact-interruption seed 1. It **failed** the acceptance
rule and is not a replacement for the baseline. All outcomes and measured sources
are preserved under `evidence/progress-recovery/first/`.

The two braking regressions entered hold but then escaped the tolerance band;
pure joint-velocity damping did not maintain the arm pose. Tracking memory
changed delay seed 2's acquisition before productive motion was established,
triggering a stall/repush sequence where frozen v2 had succeeded without retries.
These observations motivated the pose-holding brake and productive-push gate.

## Revised measured outcome

The revised 84-episode comparison **passes every acceptance check**. All 15
previous successful episodes and the successful explicit probe recoveries remain
successful. Four additional episodes succeed. Every frozen baseline rerun
reproduces its archived score, error, effort and success exactly.

| Revised variant | Nominal /5 | Mass /5 | Delay /5 | Contact /2 | Stall /2 | Crossing /2 | Total | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Frozen baseline | 5 | 2 | 3 | 2 | 2 | 1 | 15/21 | 70.4943 |
| Both new mechanisms | 5 | 4 | 5 | 2 | 2 | 1 | **19/21** | **85.7191** |
| Without tracking memory | 5 | 4 | 3 | 2 | 2 | 1 | 17/21 | 78.6149 |
| Without braking | 5 | 2 | 5 | 2 | 2 | 1 | 17/21 | 77.6959 |

Tracking memory recovers delayed seeds 0/3, ending at 14.2 mm and 11.4 mm error.
Braking recovers mass seeds 2/4, ending at 19.3 mm and 28.0 mm. The full variant's
mean squared torque decreases from 1.9056 to 1.1726. This is an effort proxy,
not measured energy. These are deterministic, repeatedly inspected development
cases; the results do not establish unseen-condition performance.

The additional successes include prevention of failure, not only retry recovery:
mass seed 2 and delay seeds 0/3 succeed without explicit retries. Mass seed 4
uses an actual approach-timeout recovery before the successful braking maneuver.
The existing contact/stall/crossing probe recovery successes are retained.

The two remaining failures are mass seed 0 (102.4 mm final error) and crossing
seed 0 (100.0 mm). Both report `no_feasible_contact_plan`. Their bounded local
search failure is not proof that no globally reachable contact pose exists.
Alternate collision-free contact plans are the next specific research target.

Both attempts preserve **168 raw episodes**, including the failed first attempt,
and their measured source snapshots. Re-score them without simulator/model calls:

```powershell
python -s -m evaluation.progress_comparison --verify docs/evidence/progress-recovery/first
python -s -m evaluation.progress_comparison --verify docs/evidence/progress-recovery/productive-contact
```

To repeat the separate developer comparison, choose a new output directory:

```powershell
python -s -m evaluation.progress_comparison --output experiments/progress-recovery/NEW_RUN
```

No agent-authored improvement is claimed. Frozen v2 still uses the 15/21
controller; its existing model candidate and result remain unchanged. This
19/21 controller is a developer candidate for a future separately versioned
strategy experiment. V2's remaining 4 evaluations, 9 trials and 3 saves were
not spent or reset, and no new held-out evaluation was opened.

Final verification: **133 tests passed**. All 114 files recorded in the
comparison's protected-artifact map remain byte-for-byte unchanged, the original
and v2 protocol locks verify, and v2's state/audit still match the published
agent receipts. See `evidence/progress-recovery/preservation.json`.
