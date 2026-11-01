# Recorded final demonstration

Video: [realityshift_demo.mp4](../demo/assets/realityshift_demo.mp4).
Duration: 88 seconds, 1280×720, 20 fps, captioned without narration.
Evidence manifest: `demo/assets/realityshift_demo.json`.

## Storyboard

| Time | Content | Evidence |
| --- | --- | --- |
| 0–8 s | Question and simulation scope | Recorded-data disclosure |
| 8–23 s | Nominal success versus high-mass failure | Initial v1, development seed 2 |
| 23–35 s | TrueForge's actual tool workflow | Session ID and saved tool calls/responses |
| 35–47 s | Persistent v1-to-v4 skill changes | Agent-generated YAML values |
| 47–62 s | Same high-mass case, v1 versus v4 | Synchronized seed-2 replays |
| 62–74 s | Complete development suite and random search | Scores 35.24, 41.83 and 44.62 |
| 74–88 s | First unseen-seed results and limitations | Held-out regression; Shelled pending |

The development seed is selected to illustrate an actual improvement, and the
video explicitly discloses this selection. The selected run is not presented as
the entire benchmark. The full suite also includes a nominal seed that regressed
under v4. The random-search baseline has a higher development score, and the
first held-out results did not improve. No experiments or tuning were performed
while creating this video.

Every replayed observation and applied action is checked against its recorded
trajectory. Report hashes and frozen benchmark fingerprints are checked too.
The manifest records the video hash, source hash, scene timings, trace hashes and
selected seed. All seven scene preview images were visually inspected; all video
frames were decoded for output verification. API keys and private runtime data
are not embedded in the video or published manifest.

## Rebuild

In the original workspace, with the recorded bridge evaluation directories:

```powershell
python -s -m pip install -r requirements-demo.txt
python -s -m demo.final_demo --output experiments/demo/rebuilt_final.mp4
```

The builder refuses to overwrite an existing output. A fresh clone includes the
finished MP4, manifest and published experiment reports, but not the full raw
trajectory directories under `.runtime/bridge/evaluations/`. The original raw
recordings are required for an exact rebuild. Running new evaluations is a
replication, not the original sponsor session, and must be labeled accordingly.

## Remaining sponsor requirement

The demo is developer-produced. Genuine Shelled implementation work and real PR
provenance remain incomplete because the workspace is not accessible in this
session. See `SHELLED_TASKS.md` and its two ready-to-run briefs. Do not submit the
project as having completed Shelled's PR requirements until real run/PR/merge
evidence has been collected.
