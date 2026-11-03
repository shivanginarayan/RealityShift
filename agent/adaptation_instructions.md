# RealityShift v3: evidence-based robotic recovery

Use only the six RealityShiftAdaptationV3 tools. No shell, web, extra instruction
packs, arbitrary code, hidden dynamics or final-test data. Numeric gains and
scoring are fixed. The available controller primitives are developer-authored;
your contribution is the actual saved strategy decision and its evaluation.

1. Get status and read the strategy catalog. Evaluate `initial` on the entire
   validation suite FIRST. A trial is not a baseline evaluation. The bridge
   enforces baseline-first and returns the same completed baseline on repetition.
2. Diagnose failing behavior through listed development trials. Opaque IDs do
   not identify physics. Low early response, tracking error, saturation and
   oscillation are observations, not estimates of mass or actuator latency.
   Marker proximity does not measure contact forces. A small tracking gap with
   slow productive pushing differs from failure to acquire contact.
3. Form a hypothesis, choose the recovery family and bounded enum strategies
   from the catalog, then save a unique version >=2. The template illustrates
   valid syntax; your actual choices must be supported by observed behavior.
   Inspect the saved diff, including simultaneous changes you did not intend.
4. Evaluate the revision on the same full validation suite. Compare matching
   condition IDs, successes, final errors, effort and actual recovery decisions.
   Never compare a few trials with a full evaluation and call it improvement.
5. If measured improvement preserves all initial successful validation tasks,
   call promote_strategy with genuine evaluation run IDs. A claimed promotion
   is not a promotion tool call. Preserve and report every failed candidate.
6. You have six full validation evaluations INCLUDING initial, twelve development
   trials, and four saves. Do not rerun identical policies unnecessarily. Stop
   when evidence or budgets warrant it. If no candidate improves, report that.
   This task authorizes the experiment; do not ask for permission to continue.

Summarize actual run IDs and before/after measurements. Distinguish improved
tracking, preventing overshoot and explicit retry recovery. Do not claim clinical
validation, hardware transfer, unseen generalization or agent-written primitive
code. Validation guides selection; only the separately reserved final test can
assess unobserved seeds/settings after all choices are frozen.
