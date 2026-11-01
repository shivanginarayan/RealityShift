"""Compose a captioned final demo from verified recorded data, without new trials."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from control.skill_schema import load_skill
from demo.render_replay import Replay
from evaluation.benchmark import ROOT, source_hash, verify_frozen

FPS = 20
SIZE = (1280, 720)


def font(size):
    for path in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def panel(title, lines, eyebrow="REALITYSHIFT / SIMULATED PHYSICS ADAPTATION"):
    image = Image.new("RGB", SIZE, "#0b1220")
    draw = ImageDraw.Draw(image)
    draw.text((48, 35), eyebrow, font=font(18), fill="#67e8f9")
    draw.text((48, 90), title, font=font(38), fill="white")
    for i, line in enumerate(lines):
        draw.text((48, 175 + i * 48), line, font=font(25), fill="#e2e8f0")
    draw.text((48, 675), "Recorded experiments. No live hardware. Full outcomes disclosed.",
              font=font(18), fill="#94a3b8")
    return np.asarray(image)


def pair_frame(left, right, title, subtitle):
    image = Image.new("RGB", SIZE, "#0b1220")
    draw = ImageDraw.Draw(image)
    draw.text((24, 16), title, font=font(30), fill="white")
    draw.text((24, 60), subtitle, font=font(19), fill="#67e8f9")
    for x, replay in ((0, left), (640, right)):
        version = replay.summary.get("skill_version", 1)
        label = replay.summary["scenario"].replace("_", " ")
        error = np.linalg.norm(replay.obs[17:19] - replay.obs[20:22])
        draw.text((x + 24, 100), f"{label.upper()} / skill v{version}", font=font(23), fill="white")
        draw.text((x + 24, 135), f"seed {replay.summary['seed']} | t={replay.index * .05:.2f}s | error {error:.3f} m",
                  font=font(20), fill="#cbd5e1")
        image.paste(Image.fromarray(replay.frame()).crop((0, 80, 640, 560)), (x, 180))
        outcome = "SUCCESS" if replay.summary["success"] else "FAILURE"
        draw.text((x + 24, 675), f"Recorded outcome: {outcome}", font=font(21),
                  fill="#86efac" if replay.summary["success"] else "#fca5a5")
    return np.asarray(image)


def build(output, bridge_directory=None):
    verify_frozen()
    output = Path(output)
    if output.suffix.lower() != ".mp4":
        raise ValueError("Choose an MP4 output")
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError("Demo already exists; choose another output filename")
    output.parent.mkdir(parents=True, exist_ok=True)
    bridge_directory = Path(bridge_directory) if bridge_directory else ROOT / ".runtime/bridge"
    evidence = json.loads((ROOT / "docs/evidence/nemotron/summary.json").read_text())
    runs = {r["skill_id"]: r for r in evidence["evaluations"]}
    base_dir = bridge_directory / "evaluations" / runs["initial"]["run_id"]
    adapted_dir = bridge_directory / "evaluations" / runs["v0004"]["run_id"]
    for name, directory in (("initial", base_dir), ("v0004", adapted_dir)):
        if source_hash(directory / "report.json") != runs[name]["report_sha256"]:
            raise ValueError("Development report changed")
    heldout = json.loads((ROOT / "docs/evidence/nemotron/heldout-report.json").read_text())
    random_report = json.loads((ROOT / "docs/RANDOM_SEARCH_V1.json").read_text())
    initial = load_skill(ROOT / "skills/initial.yaml")
    revised = load_skill(ROOT / "skills/versions/v0004.yaml")
    changes = [f"{key}: {getattr(initial, key)}  ->  {getattr(revised, key)}"
               for key in ("proportional_gain", "approach_offset", "approach_height", "push_offset",
                           "stop_distance", "action_smoothing")]
    selected_random = next(r for r in random_report["records"] if r["label"] == random_report["selected"])
    timeline = []
    frames = 0
    temporary = output.with_name(output.stem + ".partial.mp4")
    if temporary.exists():
        raise ValueError("Partial demo output already exists")
    try:
        with imageio.get_writer(str(temporary), fps=FPS, codec="libx264", quality=8, macro_block_size=16) as writer:
            def still(title, lines, seconds):
                nonlocal frames
                frame = panel(title, lines)
                timeline.append({"start_seconds": frames / FPS, "title": title, "seconds": seconds})
                for _ in range(seconds * FPS):
                    writer.append_data(frame)
                frames += seconds * FPS
                imageio.imwrite(output.with_name(output.stem + f"-{len(timeline):02d}.png"), frame)

            def pair(left_path, right_path, title, subtitle):
                nonlocal frames
                with ExitStack() as stack:
                    left = stack.enter_context(Replay(left_path))
                    right = stack.enter_context(Replay(right_path))
                    if left.summary["seed"] != right.summary["seed"] or len(left.rows) != len(right.rows):
                        raise ValueError("Comparison must have paired seeds and horizons")
                    if left.summary["controller_sha256"] != right.summary["controller_sha256"]:
                        raise ValueError("Controller implementation differs")
                    timeline.append({"start_seconds": frames / FPS, "title": title,
                                     "seconds": len(left.rows) / FPS,
                                     "left_trace_sha256": left.summary["trajectory_sha256"],
                                     "right_trace_sha256": right.summary["trajectory_sha256"]})
                    for _ in left.rows:
                        left.advance()
                        right.advance()
                        frame = pair_frame(left, right, title, subtitle)
                        writer.append_data(frame)
                        frames += 1
                    imageio.imwrite(output.with_name(output.stem + f"-{len(timeline):02d}.png"), frame)

            still("A controller works. The physics changes.", [
                "Can an agent diagnose failure and retain a better pushing skill?",
                "MuJoCo Pusher / fixed 300-step episodes / bounded joint torques",
                "TrueForge orchestrates NVIDIA Nemotron through six restricted tools.",
                "This demo uses saved trajectories; every replayed state is verified."], 8)
            pair(base_dir / "nominal/seed2", base_dir / "high_mass/seed2",
                 "1 / Same controller, shifted physics", "Development seed 2. Selected illustration; suite results follow.")
            still("2 / Actual TrueForge tool execution", [
                "NVIDIA Nemotron: get_status -> evaluate_candidate(initial)",
                "run_trial -> save_candidate_skill -> evaluate_candidate",
                "v2 failed. v3 failed. v4 passed the fixed promotion gate.",
                f"Session: {evidence['session_id']}",
                "Saved tool calls and responses: docs/evidence/nemotron/", 
                "Four evaluations total; budgets and evaluator never reset."], 12)
            still("3 / The agent's persistent skill revision", changes + [
                "Agent-generated YAML; numeric controls only, no new recovery algorithm."], 12)
            pair(base_dir / "high_mass/seed2", adapted_dir / "high_mass/seed2",
                 "4 / Same shift and seed, revised skill", "Selected development improvement. Score rules and controller code unchanged.")
            b, a = runs["initial"]["aggregate"], runs["v0004"]["aggregate"]
            still("5 / Full development results", [
                f"Initial v1: {b['successes']}/15 successes | score {b['score']:.2f}",
                f"Agent v4: {a['successes']}/15 successes | score {a['score']:.2f}",
                f"Random search: score {selected_random['aggregate']['score']:.2f} (higher than agent)",
                "One development seed also regressed under v4.",
                "A successful clip is not a claim of robust generalization."], 12)
            h0, h1 = (heldout["skills"][k]["aggregate"] for k in ("initial", "candidate"))
            still("6 / Unseen seeds: improvement did not generalize", [
                f"Initial v1: {h0['successes']}/15 | score {h0['score']:.2f}",
                f"Frozen v4: {h1['successes']}/15 | score {h1['score']:.2f}",
                "Final results preserved. No further tuning against these seeds.",
                "Measured development adaptation; held-out regression disclosed.",
                "Shelled-authored PR evidence is still pending."], 14)
        temporary.replace(output)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    manifest = {"kind": "recorded_final_demonstration", "fps": FPS, "frames": frames,
                "duration_seconds": frames / FPS, "timeline": timeline,
                "session_id": evidence["session_id"], "selected_seed": 2,
                "selection_disclosure": "Seed 2 illustrates a known development improvement; full suites shown.",
                "video_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "source_sha256": source_hash(Path(__file__)),
                "heldout_results_changed": False, "new_simulation_trials": 0}
    output.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Verified final demonstration: {output} ({frames / FPS:.0f} seconds)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "demo/assets/realityshift_demo.mp4")
    args = parser.parse_args()
    build(args.output)
