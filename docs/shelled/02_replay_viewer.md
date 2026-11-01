# Shelled task Portable paired replay viewer

Build a portable offline viewer for recorded RealityShift MP4s and their JSON
evidence manifests. Open a distinct real PR against main and preserve the Shelled
run URL, exact prompt, tests and UI screenshots. Code must genuinely be produced
through Shelled. The developer-authored final video is an input, not your work.

Implement a small viewer with synchronized playback, play/pause, restart,
scrubbing, keyboard controls, playback-rate selection and accessible labels.
Load user-selected local media/manifests; do not upload data or require an API key,
model endpoint, external CDN or a backend. Include clear error handling for
missing media, invalid manifests and incompatible timelines. Avoid embedding
untrusted manifest text as HTML. Preserve the original media and evidence files.

Display scenario, seed, skill version, success criteria, recorded outcomes and
aggregate results. Clearly distinguish selected development clips from complete
suite metrics. Always show the held-out regression and the higher random-search
score when displaying this experiment. Never label the project robust sim-to-real
transfer or claim a new evaluation took place merely by viewing artifacts.

Reuse `demo/assets/realityshift_demo.mp4` and its manifest where appropriate.
Add a concise README with local opening/serving instructions. Do not change
frozen evaluator/simulator/controller files, initial skill, candidate skill values,
benchmark locks, recorded outcome reports or held-out seeds. Add substantive
manifest/error tests and verify actual playback/UI with visible evidence.

Acceptance: functional viewer, genuine Shelled code and reviewed PR, accessible
playback controls, safe manifest rendering, no network data transmission,
reproducible validation and screenshots, existing checks and frozen hashes pass.
