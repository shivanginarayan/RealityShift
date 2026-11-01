"""Render paired recorded runs, verifying every simulated observation."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.metadata
import json
from pathlib import Path

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw

from simulation.environment import ShiftedPusher
from evaluation.benchmark import verify_frozen
from evaluation.metrics import score_episode


class Replay:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.summary = json.loads((self.directory / "summary.json").read_text())
        trajectory = self.directory / "trajectory.jsonl"
        if hashlib.sha256(trajectory.read_bytes()).hexdigest() != self.summary["trajectory_sha256"]:
            raise ValueError("Recorded trajectory hash mismatch")
        self.rows = [json.loads(line) for line in trajectory.read_text().splitlines()]
        if len(self.rows) != self.summary["steps"] or not self.rows:
            raise ValueError("Incomplete recorded episode")
        for i, row in enumerate(self.rows, 1):
            if row["step"] != i:
                raise ValueError("Recorded steps are out of sequence")
        spec, _ = verify_frozen()
        metrics = score_episode(self.rows, spec)
        if not metrics["eligible"] or metrics["success"] != self.summary["success"]:
            raise ValueError("Recorded outcome disagrees with independently scored trajectory")
        self.env = ShiftedPusher(self.summary["scenario"], self.summary["horizon"])
        try:
            obs, _ = self.env.reset(seed=self.summary["seed"])
            np.testing.assert_allclose(obs, self.rows[0]["observation_before"], atol=1e-9, rtol=0)
            manifest = self.summary["developer_physics_manifest"]
            if self.env.developer_manifest() != manifest:
                raise ValueError("Current physics configuration differs from recorded run")
            for package in ("gymnasium", "mujoco", "numpy"):
                if importlib.metadata.version(package) != self.summary["versions"][package]:
                    raise ValueError(f"Replay package version differs: {package}")
        except Exception:
            self.env.close()
            raise
        self.index = 0
        self.obs = obs
        self.renderer = None

    def advance(self):
        row = self.rows[self.index]
        np.testing.assert_allclose(self.obs, row["observation_before"], atol=1e-9, rtol=0)
        self.obs, _, terminated, truncated, _ = self.env.step(np.asarray(row["action"]))
        np.testing.assert_allclose(self.obs, row["observation_after"], atol=1e-9, rtol=0)
        np.testing.assert_allclose(self.env.last_applied_action, row["applied_action"], atol=1e-9, rtol=0)
        if terminated != row["terminated"] or truncated != row["truncated"]:
            raise ValueError("Episode boundaries differ from recording")
        self.index += 1

    def frame(self):
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.env.unwrapped.model, height=480, width=640)
        camera = mujoco.MjvCamera()
        camera.lookat[:] = [.45, -.25, -.20]
        camera.distance = 1.45
        camera.azimuth = 90
        camera.elevation = -55
        self.renderer.update_scene(self.env.unwrapped.data, camera=camera)
        picture = Image.fromarray(self.renderer.render())
        canvas = Image.new("RGB", (640, 560), "#111827")
        canvas.paste(picture, (0, 80))
        draw = ImageDraw.Draw(canvas)
        scenario = self.summary["scenario"].replace("_", " ")
        error = float(np.linalg.norm(self.obs[17:19] - self.obs[20:22]))
        draw.text((16, 10), f"{scenario.upper()}  |  seed {self.summary['seed']}", fill="white")
        draw.text((16, 30), f"t={self.index * self.env.unwrapped.dt:.2f}s  |  target error={error:.3f}m", fill="white")
        label = "Recorded outcome: SUCCESS" if self.summary["success"] else "Recorded outcome: FAILURE"
        version = self.summary.get("skill_version", 1)
        draw.text((16, 50), f"{label}  |  skill v{version}", fill="#86efac" if self.summary["success"] else "#fca5a5")
        return np.asarray(canvas)

    def close(self):
        if self.renderer is not None:
            self.renderer.close()
        self.env.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def render(left_path, right_path, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError("Output already exists; choose a new filename")
    temporary = output.with_name(output.stem + ".partial.mp4")
    if temporary.exists():
        raise ValueError("Temporary output already exists")
    with ExitStack() as stack:
        left = stack.enter_context(Replay(left_path))
        right = stack.enter_context(Replay(right_path))
        if left.summary["seed"] != right.summary["seed"] or len(left.rows) != len(right.rows):
            raise ValueError("Paired replays require matching seed and episode length")
        if left.summary["controller_sha256"] != right.summary["controller_sha256"]:
            raise ValueError("Paired replays require the same recorded controller")
        if left.summary.get("skill_sha256") != right.summary.get("skill_sha256"):
            raise ValueError("Paired replays require the same recorded skill")
        if left.env.unwrapped.dt != right.env.unwrapped.dt:
            raise ValueError("Paired replays require equal time steps")
        try:
            with imageio.get_writer(str(temporary), fps=round(1 / left.env.unwrapped.dt), codec="libx264",
                                    macro_block_size=16, quality=8) as writer:
                for _ in left.rows:
                    left.advance()
                    right.advance()
                    frame = np.concatenate([left.frame(), right.frame()], axis=1)
                    writer.append_data(frame)
                    if left.index == len(left.rows):
                        imageio.imwrite(output.with_suffix(".png"), frame)
            temporary.replace(output)
            evidence = {"kind": "recorded_simulation_replay_no_adaptation", "frames": len(left.rows),
                        "fps": round(1 / left.env.unwrapped.dt), "every_observation_verified": True,
                        "left": left.summary, "right": right.summary,
                        "video_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
            output.with_suffix(".json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        except Exception:
            if temporary.exists():
                temporary.unlink()
            raise
    print(f"Verified and rendered {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.left, args.right, args.output)
