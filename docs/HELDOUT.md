# Final evaluation protocol

The protocol is reserved before agent adaptation. It compares the initial skill
with one finalized candidate on fifteen episodes each: five new seeds across the
same three scenario settings. It measures generalization to unseen initial-state
seeds, not unseen mass/delay ranges or real hardware.

The protocol has now been executed once on frozen agent skill v4, after its
development budget was exhausted. Initial and v4 each succeeded 5/15; initial
scored 36.4483 and v4 scored 34.6993. Thus v4 did not improve on unseen seeds.
Tests separately use synthetic fixtures to check pairing and access controls.
The agent bridge accepts only development seeds and exposes no held-out tool.

After the actual agent has finalized its candidate and its development evaluation
has recorded the canonical skill hash, run locally as the developer:

```powershell
python -s -m evaluation.heldout --skill skills/versions/v0002.yaml --skill-sha256 FINAL_DEVELOPMENT_SKILL_HASH
```

Substitute the actual final version and hash. The command validates the schema,
requires version 2 or higher, checks the supplied hash, and snapshots both skills
before observing outcomes. It reuses benchmark v1's frozen scorer without changing
its thresholds. A separate lock fingerprints the held-out protocol and runner.

Outputs go to `experiments/final/`. A persistent reservation at
`.runtime/heldout-receipt.json` prevents accidental repeat access, even if another
output path is used internally. Reservations occur before any episodes execute;
a partial failure leaves the reservation in place. Do not delete it to tune
against final results. Preserve partial evidence and disclose infrastructure
failures if a supervised recovery becomes necessary.

The receipt is a developer workflow guard, not a security boundary against
someone with full filesystem access. Changing source locks or seed definitions
requires a new disclosed protocol. Do not use final results for further tuning
and then describe the same seeds as held out.

Actual TrueForge session provenance must accompany any agent-authorship claim;
the evaluator does not establish authorship. The recorded session used NVIDIA
Nemotron; no further OpenAI calls were made after the initial no-credit error.
See AGENT_RESULTS.md and evidence/nemotron/ for real tool execution and outcomes.

The first final report and all thirty original final trajectories are preserved
in `evidence/nemotron/`. Offline verification re-scores those bytes; it does not
consume another final evaluation or expose further feedback to the agent.
Mean issued squared torque was 2.8379475194 for v1 versus 2.6765368776 for v4;
both had zero ineligible episodes. This effort reduction did not compensate for
worse target error and score. The generalization improvement gate failed.
