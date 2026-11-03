"""Self-contained replay of the actual final-test stall/repush from public evidence."""
import hashlib
import json
import zipfile
from pathlib import Path

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw

from demo.adaptation_demo import font
from evaluation.benchmark import ROOT, source_hash
from evaluation.metrics import score_episode
from evaluation.v3.benchmark import spec
from simulation.delay_shift import DelayedPusher


def render():
    archive = ROOT / 'docs/evidence/adaptation-v3/experiment/trajectories.zip'
    index = json.loads((archive.parent / 'archive.json').read_text())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != index['sha256']['trajectories.zip']:
        raise ValueError('Public trajectory archive changed')
    with zipfile.ZipFile(archive) as bundle:
        reports = {label: json.loads(bundle.read(f'final/{label}/report.json')) for label in ('original', 'trueforge')}
        choices = [e for e in reports['trueforge']['episodes'] if e['success'] and any(
            event['reason'] == 'stall' and event['strategy'] == 'repush' for event in e['strategy_events'])]
        if not choices:
            raise ValueError('No genuine final-test stall/repush success; do not simulate one for the demo')
        selected = choices[0]
        condition = next(c for c in spec()['splits']['heldout'] if c['id'] == selected['condition_id'])
        episodes, histories = [], []
        for label in ('original', 'trueforge'):
            episode = next(e for e in reports[label]['episodes'] if e['condition_id'] == condition['id'])
            raw = bundle.read(f"final/{label}/{condition['id']}/trajectory.jsonl")
            if hashlib.sha256(raw).hexdigest() != episode['trajectory_sha256']:
                raise ValueError('Replay trajectory changed')
            rows = [json.loads(line) for line in raw.splitlines()]
            if any(episode[k] != value for k, value in score_episode(rows, spec()).items()):
                raise ValueError('Replay score differs')
            episodes.append(episode)
            histories.append(rows)
    output = ROOT / 'demo/assets/realityshift_heldout_repush_v3.mp4'
    if output.exists():
        raise ValueError('Preserve existing replay; do not overwrite')
    envs, renderers, observations = [], [], []
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [.45, -.25, -.20]
    camera.distance, camera.azimuth, camera.elevation = 1.45, 90, -55
    try:
        for _ in range(2):
            env = DelayedPusher(condition['delay_steps'], condition['onset_step'])
            obs, _ = env.reset(seed=condition['seed'])
            envs.append(env)
            observations.append(obs)
            renderers.append(mujoco.Renderer(env.unwrapped.model, height=480, width=640))
        np.testing.assert_array_equal(observations[0], observations[1])
        with imageio.get_writer(str(output), fps=20, codec='libx264', quality=8, macro_block_size=16) as writer:
            for i in range(300):
                canvas = Image.new('RGB', (1280, 640), '#091422')
                draw = ImageDraw.Draw(canvas)
                for side, (env, renderer, rows) in enumerate(zip(envs, renderers, histories)):
                    row = rows[i]
                    np.testing.assert_allclose(observations[side], row['observation_before'], atol=1e-9, rtol=0)
                    obs, _, terminated, truncated, _ = env.step(np.asarray(row['action']))
                    np.testing.assert_allclose(obs, row['observation_after'], atol=1e-9, rtol=0)
                    np.testing.assert_allclose(env.last_applied_action, row['applied_action'], atol=1e-9, rtol=0)
                    if terminated != row['terminated'] or truncated != row['truncated']:
                        raise ValueError('Replay boundary changed')
                    observations[side] = obs
                    renderer.update_scene(env.unwrapped.data, camera=camera)
                    x = side * 640
                    canvas.paste(Image.fromarray(renderer.render()), (x, 80))
                    title = 'ORIGINAL / FINAL-TEST FAILURE' if side == 0 else 'TRUEFORGE POLICY / STALL + REPUSH'
                    draw.text((x+18, 12), title, font=font(20, True), fill='#ff969f' if side == 0 else '#79edc1')
                    stage = row['command_stage']
                    error = np.linalg.norm(obs[17:19] - obs[20:22])
                    draw.text((x+18, 44), f"t={(i+1)*.05:.2f}s | {stage} | error {100*error:.1f} cm", font=font(18), fill='white')
                    if side and stage in ('repush_backoff', 'repush'):
                        draw.rounded_rectangle((x+18, 490, x+600, 544), radius=10, fill='#14523e')
                        draw.text((x+32, 505), 'ACTUAL BOUNDED RECOVERY: ' + stage.upper(), font=font(18, True), fill='#99f9cc')
                    draw.text((x+18, 578), 'First final evaluation | 250 ms delay | same starting state', font=font(17), fill='#acc0da')
                    draw.text((x+18, 607), 'Recorded events: stall -> backoff -> repush -> settled success' if side else 'Original issued commands replayed without changes', font=font(16), fill='#79edc1' if side else '#b7c6dc')
                writer.append_data(np.asarray(canvas))
    finally:
        for renderer in renderers:
            renderer.close()
        for env in envs:
            env.close()
    output.with_suffix('.json').write_text(json.dumps({'kind': 'verified_final_stall_repush_replay',
        'condition': condition, 'source_archive_sha256': index['sha256']['trajectories.zip'],
        'every_observation_and_applied_command_verified': True, 'strategy_events': selected['strategy_events'],
        'left_success': episodes[0]['success'], 'right_success': episodes[1]['success'],
        'video_sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'source_sha256': source_hash(Path(__file__))}, indent=2) + '\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    render()
