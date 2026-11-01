# Conventional random-search baseline

This is a developer-run conventional optimizer, not an agent-authored skill or
TrueForge self-improvement result. It provides a sanity check for future agent
results on the frozen development benchmark.

Reproduce from the repository root:

```powershell
python -s -m evaluation.baselines --sampler-seed 42
```

The program evaluates the initial skill once and three sampled candidate skills:
four full evaluations, fifteen episodes each. The candidate count matches the
bridge's four-evaluation cap including baseline. It does not consume or reset
the bridge's budgets. It runs no diagnostics; an agent can additionally use up
to twelve diagnostic episodes, so equal full-evaluation count is not equal total
simulation cost. Report diagnostic counts alongside later comparisons.

Sampling uses Python's seeded `random.Random`, sorted control-field names and
independent uniform draws across each field's published validation bounds. All
three samples, seed, bounds, benchmark hashes and sampler source hash are saved
before evaluation begins. This broad three-sample search is a small sanity
baseline, not a tuned optimization algorithm or a statistical significance test.

Candidate YAML and raw evaluations stay under a fresh
`experiments/random_search/<timestamp>/` directory, separate from agent candidates
and promotion state. The initial skill is never replaced. A running incumbent
is retained unless a candidate passes eligibility, strictly improves scalar
score, and improves the evaluator's lexicographic task ranking. Every outcome is
preserved, including rejected candidates. Held-out scenarios are not used.

See `RANDOM_SEARCH_V1.json` for the recorded run summary. Reproduce raw
trajectories with the command above. No claims of autonomous adaptation should
be based on these results.

Recorded run: `experiments/random_search/20261101T070658694676Z/`.

| Skill | Successes | Fixed score | Decision |
| --- | --- | --- | --- |
| Initial | 5/15 | 35.2412 | Starting incumbent |
| Random 1 | 3/15 | 24.8116 | Rejected |
| Random 2 | 6/15 | 44.6180 | Selected |
| Random 3 | 0/15 | 7.9082 | Rejected |

Random 2 is sampler version 3, not an agent-authored v3 skill. Its parameters
and hashes are in the tracked report; the YAML is under the run's `sampled_skills`
directory. There is no held-out evidence for this skill. All sixty development
episodes completed; the original frozen benchmark remains unchanged.
