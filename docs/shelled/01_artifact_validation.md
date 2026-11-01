# Shelled task Artifact integrity validation

Implement substantive new code in `diagnostics/validate_artifact.py` and tests
in `tests/test_artifact_validation.py`. Open a real PR against main and preserve
the Shelled run URL and prompt. Do not modify any file listed in
`evaluation/frozen.json` or `evaluation/heldout_frozen.json`, nor either lock.
Preserve recorded experiment outcomes and the first held-out results.

Build a CLI that validates a recorded episode directory without simulating:

- Verify summary/trajectory presence and the trajectory SHA-256 hash.
- Validate row types, finite observations/actions, exact dimensions, contiguous
  steps and timestamps, observation continuity, and episode completion.
- Check terminal/truncated flags occur only at valid episode boundaries and that
  summary step count, target error and success agree with independently computed
  metrics from the frozen scorer. Never trust claimed error/reward fields.
- Report every supported invalid-artifact case with structured error codes and
  return a nonzero exit code; do not crash or mutate the input on malformed data.
- Bound file/row sizes and reject path traversal in any metadata references.
- Include actual reproduction commands, expected and observed outcomes in
  EDGE_CASES.md after running tests. Do not invent trial outcomes.

Add meaningful adversarial tests for corrupted hashes, truncated files, invalid
JSON, missing/wrong-type fields, invalid dimensions, NaN/Infinity, discontinuous
states, repeated/missing steps, wrong timestamps, early termination flags and
forged summaries. Existing tests and frozen hashes must remain valid.

Acceptance: substantive validator implementation, reviewable PR, recorded Shelled
provenance, adversarial tests passing, no credentials or runtime databases in Git.
