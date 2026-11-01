# Final evaluation protocol

The protocol is reserved before agent adaptation. It compares the initial skill
with one finalized candidate on fifteen episodes each: five new seeds across the
same three scenario settings. It measures generalization to unseen initial-state
seeds, not unseen mass/delay ranges or real hardware.

No actual held-out simulation has been executed. Tests use synthetic observation
fixtures to check pairing and access controls; those are not experiment results.
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
the evaluator does not establish authorship. OpenAI provider configuration and
the first real adaptation run remain pending. The next core action is to enter
the OpenAI API key in TrueForge's local Settings → Models page.
