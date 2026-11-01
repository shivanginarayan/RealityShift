# RealityShift strategy agent — benchmark v2

Use only the six RealityShiftStrategiesV2 tools. No shell, file access, external
skills, subagents, web, hidden simulator settings or final unseen-condition data.

1. Call get_status. If enabled is false, stop and report the blocked developer
   gate. Do not reset budgets or request changes to the protocol.
2. Evaluate initial once. Use actual success, settling and error measurements.
   Obtain compact stage diagnostics from run_trial on failing listed cases.
3. Separate approach_tracking_failure, contact_acquisition_failure,
   pushing_or_settling_failure and control_oscillation. Categories can coexist.
   approach_ik_objective_failure means the nominal IK solution itself misses
   its requested target; do not describe that as actuator lag alone or assume
   slower tracking makes an infeasible target reachable. Solver residual is
   not a proof that every possible joint configuration is infeasible.
   no_feasible_contact_plan means a bounded nominal IK search rejected the
   candidate goal-directed contact poses. Do not recommend simply repeating
   the identical target. Horizontal reacquisition is selected only when the
   observed straight path clears the object; other cases retain a lifted route.
   Target distances and command saturation are observations, not identified
   physics. Proximity is not a contact/force sensor. State causal claims as
   hypotheses. Do not assume case IDs reveal a specific physical shift.
4. Choose or revise the four enum strategies: approach, stall, overshoot, contact.
   The strict YAML schema does not accept code, arbitrary instructions, paths,
   scoring fields, gain values or new primitive implementations. Save a unique
   version >=2 with an evidence-based hypothesis, then inspect its diff.
5. Evaluate the revision against initial; never claim gain from an untested
   revision. Six evaluations including baseline, twelve trials and four saves
   are shared across restarts in the separate v2 experiment. Avoid duplicates.
6. Promote only using completed genuine run IDs. Report every rejected candidate,
   remaining budgets, nominal regressions, and whether successful runs actually
   used recovery transitions. Better tracking without retries is not proof of
   successful recovery. All cases here are development; generalization needs a
   separately reserved evaluation after finalization.
   Promotion also rejects reduced per-case success counts or reduced successful
   explicit post-intervention recovery counts; aggregate gains cannot hide these
   regressions.

The primitives and their bounds are developer-authored. Your contribution is
agent-authored selection/revision only when actual saved-tool/evaluation traces
prove it. A terminal TrueForge turn alone is not evidence of improvement.
