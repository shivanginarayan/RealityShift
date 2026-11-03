"""Authentic v3 arm replays and a 75-second agent-decision demonstration."""
import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import textwrap

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from evaluation.benchmark import ROOT, source_hash
from evaluation.metrics import score_episode
from evaluation.v3.benchmark import spec, verify
from simulation.delay_shift import DelayedPusher


CACHE = ROOT / '.runtime/adaptation-v3/demo'
RUNTIME = ROOT / '.runtime/adaptation-v3'
COLORS = [(1., .42, .43, 1.), (.28, .94, .73, 1.)]


@lru_cache(maxsize=20)
def font(size, bold=False):
    name = 'arialbd.ttf' if bold else 'arial.ttf'
    path = Path('C:/Windows/Fonts') / name
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def wrapped(draw, value, xy, width=47, size=23, color='#c0d1e8', spacing=33):
    x, y = xy
    for line in textwrap.wrap(value, width=width):
        draw.text((x, y), line, font=font(size), fill=color)
        y += spacing
    return y


def sources():
    verify()
    state = json.loads((RUNTIME / 'state.json').read_text())
    audit = [json.loads(line) for line in (RUNTIME / 'audit.jsonl').read_text().splitlines()]
    decisions = [e for e in audit if e['operation'] == 'promotion_decision' and e['accepted']]
    if not decisions:
        raise ValueError('No actual agent promotion: do not manufacture an adapted success demo')
    decision = decisions[-1]
    reports = [json.loads((RUNTIME / 'evaluations' / decision[k] / 'report.json').read_text()) for k in ('baseline', 'candidate')]
    for key in ('baseline', 'candidate'):
        if source_hash(RUNTIME / 'evaluations' / decision[key] / 'report.json') != state['runs'][decision[key]]['report_sha256']:
            raise ValueError('Actual evaluation evidence changed')
    original = {e['condition_id']: e for e in reports[0]['episodes']}
    candidate = {e['condition_id']: e for e in reports[1]['episodes']}
    conditions = spec()['splits']['validation']
    # Predeclared illustrative preference: unchanged 4-step mid-task conversion.
    choices = [c for c in conditions if c['delay_steps'] == 4 and c['onset_step'] == 60
               and not original[c['id']]['success'] and candidate[c['id']]['success']]
    if not choices:
        choices = [c for c in conditions if not original[c['id']]['success'] and candidate[c['id']]['success']]
    if not choices:
        raise ValueError('No genuine paired failure-to-success conversion')
    condition = choices[0]
    saved_id = state['runs'][decision['candidate']]['strategy_id']
    saved = next(e for e in audit if e['operation'] == 'strategy_saved' and e['strategy_id'] == saved_id)
    return state, decision, reports, condition, saved


def replay_frames(run_id, condition, color):
    directory = RUNTIME / 'evaluations' / run_id
    report = json.loads((directory / 'report.json').read_text())
    episode = next(e for e in report['episodes'] if e['condition_id'] == condition['id'])
    raw = (directory / condition['id'] / 'trajectory.jsonl').read_bytes()
    if hashlib.sha256(raw).hexdigest() != episode['trajectory_sha256']:
        raise ValueError('Replay trajectory changed')
    rows = [json.loads(line) for line in raw.splitlines()]
    scored = score_episode(rows, spec())
    if any(episode[k] != value for k, value in scored.items()):
        raise ValueError('Replay outcome differs from independent scoring')
    env = DelayedPusher(condition['delay_steps'], condition['onset_step'])
    renderer = None
    try:
        obs, _ = env.reset(seed=condition['seed'])
        renderer = mujoco.Renderer(env.unwrapped.model, height=480, width=640)
        camera = mujoco.MjvCamera()
        camera.lookat[:] = [.45, -.25, -.20]
        camera.distance, camera.azimuth, camera.elevation = 1.45, 90, -55
        path = [obs[17:20].copy()]
        for row in rows:
            np.testing.assert_allclose(obs, row['observation_before'], atol=1e-9, rtol=0)
            obs, _, terminated, truncated, _ = env.step(np.array(row['action']))
            np.testing.assert_allclose(obs, row['observation_after'], atol=1e-9, rtol=0)
            np.testing.assert_allclose(env.last_applied_action, row['applied_action'], atol=1e-9, rtol=0)
            if terminated != row['terminated'] or truncated != row['truncated']:
                raise ValueError('Replay episode boundary differs')
            path.append(obs[17:20].copy())
            renderer.update_scene(env.unwrapped.data, camera=camera)
            samples = path[::3] + [path[-1]]
            for start, end in zip(samples[:-1], samples[1:]):
                if np.linalg.norm(end-start) < .0001:
                    continue
                geom = renderer.scene.geoms[renderer.scene.ngeom]
                mujoco.mjv_initGeom(geom, mujoco.mjtGeom.mjGEOM_CAPSULE, np.zeros(3), np.zeros(3),
                                   np.eye(3).ravel(), np.asarray(color, dtype=np.float32))
                mujoco.mjv_connector(geom, mujoco.mjtGeom.mjGEOM_CAPSULE, .003,
                                     start + [0, 0, .056], end + [0, 0, .056])
                renderer.scene.ngeom += 1
            yield renderer.render(), row, episode
    finally:
        if renderer:
            renderer.close()
        env.close()


def render():
    state, decision, reports, condition, saved = sources()
    CACHE.mkdir(parents=True, exist_ok=True)
    output = CACHE / 'paired.mp4'
    if output.exists():
        raise ValueError('Choose a new version rather than overwriting replay provenance')
    left = replay_frames(decision['baseline'], condition, COLORS[0])
    right = replay_frames(decision['candidate'], condition, COLORS[1])
    with imageio.get_writer(str(output), fps=20, codec='libx264', quality=8, macro_block_size=16) as writer:
        for i, (l, r) in enumerate(zip(left, right)):
            frame = Image.new('RGB', (1280, 640), '#0b1322')
            draw = ImageDraw.Draw(frame)
            for side, (picture, row, episode) in enumerate((l, r)):
                x = side * 640
                frame.paste(Image.fromarray(picture), (x, 80))
                label = 'ORIGINAL CONTROLLER' if side == 0 else 'TRUEFORGE-SELECTED STRATEGY'
                draw.text((x+20, 12), label, font=font(21, True), fill='#ff8c94' if side == 0 else '#7af1c4')
                error = np.linalg.norm(np.asarray(row['observation_after'])[17:19] - np.asarray(row['observation_after'])[20:22])
                draw.text((x+20, 44), f"t={(i+1)*.05:4.2f}s | error {error*100:4.1f} cm | {row['command_stage']}", font=font(18), fill='#bed0e8')
                draw.text((x+20, 578), 'Colored trace: observed object XY path; red marker: goal', font=font(17), fill='#aebfd8')
                status = 'Delay begins at 3.0s' if i < 60 else 'Changed actuator response: 200 ms delay'
                draw.text((x+20, 607), status, font=font(17), fill='#f9d47a')
                if i == 299:
                    draw.rounded_rectangle((x+18, 485, x+345, 544), radius=9, fill='#13382d' if episode['success'] else '#431f29')
                    draw.text((x+34, 500), 'SETTLED SUCCESS' if episode['success'] else 'FAILED TO SETTLE', font=font(22, True), fill='#7af1c4' if episode['success'] else '#ffa2ac')
            draw.line((639, 0, 639, 640), fill='#324963', width=2)
            writer.append_data(np.asarray(frame))
            if i == 299:
                frame.save(CACHE / 'paired-final.png')
    nominal = next(c for c in spec()['splits']['validation'] if c['delay_steps'] == 0)
    with imageio.get_writer(str(CACHE / 'nominal.mp4'), fps=20, codec='libx264', quality=8, macro_block_size=16) as writer:
        for picture, _, _ in replay_frames(decision['baseline'], nominal, COLORS[0]):
            writer.append_data(picture)
    provenance = {'kind': 'verified_recorded_v3_replay', 'condition': condition,
                  'baseline_run': decision['baseline'], 'candidate_run': decision['candidate'],
                  'policy_id': state['promoted'], 'agent_hypothesis': saved['hypothesis'],
                  'every_observation_and_applied_command_verified': True,
                  'trajectory_overlay': 'Observed object XY, drawn 56 mm above its center for visibility; simulation state unchanged.',
                  'validation_original': reports[0]['aggregate'], 'validation_agent': reports[1]['aggregate'],
                  'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in CACHE.glob('*.mp4')}}
    (CACHE / 'replay.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(provenance, indent=2))


def build():
    verify()
    summary = json.loads((RUNTIME / 'final/summary.json').read_text())
    provenance = json.loads((CACHE / 'replay.json').read_text())
    for name, digest in provenance['files'].items():
        if hashlib.sha256((CACHE / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Verified replay changed before composition')
    output = ROOT / 'demo/assets/realityshift_adaptation_v3.mp4'
    if output.exists():
        raise ValueError('Final demonstration already exists; preserve original')
    pair = imageio.get_reader(str(CACHE / 'paired.mp4'))
    nominal = imageio.get_reader(str(CACHE / 'nominal.mp4'))
    first_pair = pair.get_data(0)
    last_pair = pair.get_data(299)
    fps, seconds = 20, 75
    agent_policy = (RUNTIME / 'strategies' / f"{provenance['policy_id']}.yaml").read_text()
    with imageio.get_writer(str(output), fps=fps, codec='libx264', quality=8, macro_block_size=16) as writer:
        for index in range(seconds * fps):
            t = index / fps
            image = Image.new('RGB', (1280, 720), '#08111e')
            draw = ImageDraw.Draw(image)
            draw.text((35, 24), 'REALITYSHIFT  /  TRUEFORGE DELAY ADAPTATION', font=font(18, True), fill='#69e7be')
            if t < 5:
                image.paste(Image.fromarray(first_pair).resize((1280, 640)), (0, 80))
                shade = Image.new('RGBA', image.size, (4, 12, 23, 180))
                image = Image.alpha_composite(image.convert('RGBA'), shade).convert('RGB')
                draw = ImageDraw.Draw(image)
                draw.text((65, 210), 'The robot fails. The agent changes its strategy.', font=font(38, True), fill='white')
                wrapped(draw, 'Actual robotic simulation. Actual TrueForge decisions. Independently scored outcomes.', (68, 290), 73, 27)
            elif t < 15:
                frame = nominal.get_data(min(299, int((t-5)*30)))
                image.paste(Image.fromarray(frame).resize((896, 672)), (0, 48))
                draw = ImageDraw.Draw(image)
                draw.rectangle((896, 48, 1280, 720), fill='#101e30')
                draw.text((925, 115), '1 / NORMAL PHYSICS', font=font(23, True), fill='#79edc1')
                wrapped(draw, 'The original strategy can push the object to its goal.', (925, 180), 22, 25)
                wrapped(draw, 'Recorded nominal success. 15 seconds replayed at 1.5x.', (925, 390), 26, 20)
            elif t < 25:
                frame = pair.get_data(min(299, int((t-15)*30)))
                image.paste(Image.fromarray(frame[:, :640]).resize((896, 672)), (0, 48))
                draw = ImageDraw.Draw(image)
                draw.rectangle((896, 48, 1280, 720), fill='#241a26')
                draw.text((925, 115), '2 / RESPONSE CHANGES', font=font(21, True), fill='#ff9caa')
                wrapped(draw, 'A 200 ms command delay begins at 3.0 seconds. The unchanged original strategy fails.', (925, 180), 23, 25)
                wrapped(draw, 'Same goal, torque bounds and 15-second task. Replay at 1.5x.', (925, 435), 25, 20)
            elif t < 35:
                draw.text((45, 95), '3 / THE AGENT MAKES A RECORDED DECISION', font=font(31, True), fill='white')
                wrapped(draw, 'Actual saved hypothesis', (48, 165), 60, 21, '#79edc1')
                wrapped(draw, provenance['agent_hypothesis'], (48, 210), 54, 24)
                draw.rounded_rectangle((750, 165, 1240, 570), radius=15, fill='#12263a')
                y = 190
                for line in agent_policy.splitlines():
                    draw.text((770, y), line, font=font(21), fill='#c0e4de')
                    y += 30
                draw.text((48, 445), 'Validation: original 3/21  →  agent-selected policy 21/21', font=font(26, True), fill='#79edc1')
                wrapped(draw, 'TrueForge saved s0002, evaluated all paired validation tasks and called promotion. Primitives were developer-authored.', (48, 500), 51, 22)
            elif t < 50:
                image.paste(Image.fromarray(pair.get_data(min(299, int((t-35)*20)))), (0, 80))
                draw = ImageDraw.Draw(image)
                draw.text((35, 51), '4 / SAME INITIAL STATE, SAME CHANGED PHYSICS, DIFFERENT STRATEGY', font=font(20, True), fill='white')
            elif t < 65:
                draw.text((45, 95), '5 / FIRST FINAL RESULTS — POLICIES FROZEN BEFORE TESTING', font=font(28, True), fill='white')
                wrapped(draw, 'Unseen seeds and delay settings; 25 paired conditions, five starting-seed clusters.', (48, 155), 91, 23)
                draw.text((50, 235), 'Controller', font=font(23, True), fill='#abc0dc')
                draw.text((575, 235), 'Successes', font=font(23, True), fill='#abc0dc')
                draw.text((805, 235), 'Mean goal error', font=font(23, True), fill='#abc0dc')
                labels = [('original', 'Original'), ('developer', 'Developer adaptive recovery'), ('conventional', 'Conventional enum search'), ('trueforge', 'TrueForge-selected strategy')]
                for j, (key, label) in enumerate(labels):
                    row = summary['results'][key]
                    y = 295 + 67*j
                    color = '#79edc1' if key == 'trueforge' else '#e0e9f8'
                    draw.text((50, y), label, font=font(25, key == 'trueforge'), fill=color)
                    draw.text((575, y), f"{row['successes']} / {row['episodes']}", font=font(27, True), fill=color)
                    draw.text((805, y), f"{row['mean_final_error_m']*100:.2f} cm", font=font(27), fill=color)
                wrapped(draw, 'Both searches had a cap of six validation evaluations. This is small-sample simulation evidence, not hardware or clinical validation.', (50, 610), 99, 20)
            else:
                image.paste(Image.fromarray(last_pair), (0, 80))
                image = Image.alpha_composite(image.convert('RGBA'), Image.new('RGBA', image.size, (4,12,23,205))).convert('RGB')
                draw = ImageDraw.Draw(image)
                draw.text((65, 150), 'Toward robots that adapt to degraded response.', font=font(36, True), fill='white')
                y = 235
                for line in ('Actual agent policy selection, not agent-written controller code.',
                             'Final results preserved; no tuning on the final outcomes.',
                             'A simulator research prototype for more adaptable manipulation.',
                             'No physical deployment or unsupervised assistive-care claim.'):
                    draw.text((70, y), line, font=font(25), fill='#bfd0e8')
                    y += 62
            writer.append_data(np.asarray(image))
            if index in (44*fps,):
                image.save(output.with_suffix('.png'))
    pair.close()
    nominal.close()
    metadata = {**provenance, 'duration_seconds': seconds, 'fps': fps,
                'video_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                'final_results': summary['results'], 'source_sha256': source_hash(Path(__file__)),
                'note': 'Actual recorded trajectories and actual saved agent hypothesis; no private reasoning or fabricated trajectories.'}
    output.with_suffix('.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    render() if args.render else build()
