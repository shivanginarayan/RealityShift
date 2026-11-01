"""Publish and re-score real v2 tool evidence, without private model reasoning."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from evaluation.benchmark import ROOT, source_hash
from evaluation.metrics import aggregate, score_episode
from evaluation.v2.benchmark import read_spec, verify_v2


def projection(value):
    if isinstance(value, dict):
        return {k: projection(v) for k, v in value.items() if k != 'reasoning_content'}
    if isinstance(value, list):
        return [projection(v) for v in value]
    return value


def package(runs, destination):
    verify_v2()
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    runtime = ROOT / '.runtime/strategy-v2'
    for i, run in enumerate(runs):
        run = Path(run)
        receipt = json.loads((run / 'evidence.json').read_text())
        if not receipt['terminal']:
            raise ValueError('Collect terminal session evidence before publishing')
        target = destination / f'turn{i + 1}'
        target.mkdir()
        for name in ('agent.json', 'run.json', 'evidence.json', 'supervision.json'):
            if (run / name).is_file():
                data = projection(json.loads((run / name).read_text()))
                (target / name).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        events = [projection(json.loads(line)) for line in (run / 'events.jsonl').read_text().splitlines()]
        (target / 'events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events), encoding='utf-8')
    for name in ('state.json', 'audit.jsonl'):
        (destination / name).write_bytes((runtime / name).read_bytes())
    with zipfile.ZipFile(destination / 'trajectories.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for folder in ('evaluations', 'trials', 'strategies'):
            for path in sorted((runtime / folder).rglob('*')):
                if path.is_file():
                    bundle.write(path, path.relative_to(runtime).as_posix())
        bundle.write(ROOT / 'strategies/v2/initial.yaml', 'initial.yaml')
        bundle.write(ROOT / 'evaluation/v2/frozen.json', 'frozen.json')
    index = {'authorship': 'agent_enum_selection_with_disclosed_supervision',
             'note': 'Public event projections remove reasoning_content recursively. Original raw exports remain private; their hashes are in each export receipt.',
             'sha256': {p.relative_to(destination).as_posix(): source_hash(p) if p.suffix != '.zip'
                        else hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(destination.rglob('*')) if p.is_file()}}
    (destination / 'archive.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    return verify(destination)


def verify(directory):
    directory = Path(directory)
    index = json.loads((directory / 'archive.json').read_text())
    for name, expected in index['sha256'].items():
        path = directory / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if name.endswith('.zip') else source_hash(path)
        if actual != expected:
            raise ValueError('Agent evidence changed')
    state = json.loads((directory / 'state.json').read_text())
    calls, responses = {}, {}
    for path in directory.glob('turn*/events.jsonl'):
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if projection(row) != row:
                raise ValueError('Private reasoning present in public projection')
            event = row['event']
            for call in event.get('tool_calls', []):
                calls[call['id']] = call['function']
            if event['type'] == 'tool.response':
                try:
                    responses[event['tool_call_id']] = json.loads(event['content'])
                except (ValueError, TypeError):
                    pass  # Preserve genuine error strings without treating them as metrics.
    spec, count, completed = read_spec(), 0, {}
    expected_cases = {(case, seed) for case, data in spec['cases'].items() for seed in data['seeds']}
    with zipfile.ZipFile(directory / 'trajectories.zip') as bundle:
        for name in bundle.namelist():
            if name.startswith('evaluations/') and name.endswith('/report.json'):
                report = json.loads(bundle.read(name))
                prefix = name.rsplit('/', 1)[0]
                measured = []
                if {(e['case_id'], e['seed']) for e in report['episodes']} != expected_cases or len(report['episodes']) != 21:
                    raise ValueError('Incomplete agent evaluation')
                for episode in report['episodes']:
                    raw = bundle.read(f"{prefix}/{episode['case_id']}/seed{episode['seed']}/trajectory.jsonl")
                    if hashlib.sha256(raw).hexdigest() != episode['trajectory_sha256']:
                        raise ValueError('Agent trajectory changed')
                    metric = score_episode([json.loads(line) for line in raw.splitlines()], spec)
                    if any(episode[k] != value for k, value in metric.items()):
                        raise ValueError('Agent episode score differs')
                    measured.append(metric)
                    count += 1
                if aggregate(measured) != report['aggregate']:
                    raise ValueError('Agent aggregate differs')
                run_id = prefix.split('/')[1]
                if source_hash_bytes(bundle.read(name)) != state['runs'][run_id]['report_sha256']:
                    raise ValueError('Evaluated report differs from bridge receipt')
                strategy = bundle.read(prefix + '/strategy.yaml')
                if source_hash_bytes(strategy) != report['strategy_sha256']:
                    raise ValueError('Evaluated strategy differs')
                completed[run_id] = report['aggregate']
            elif name.startswith('trials/') and name.endswith('/trajectory.jsonl'):
                score_episode([json.loads(line) for line in bundle.read(name).splitlines()], spec)
                count += 1
    if set(completed) != set(state['runs']):
        raise ValueError('Completed evaluations omitted')
    for run_id, metrics in completed.items():
        matches = [(calls[call_id], response) for call_id, response in responses.items()
                   if call_id in calls and isinstance(response, dict) and response.get('run_id') == run_id]
        if len(matches) != 1:
            raise ValueError('Missing actual evaluation response')
        call, response = matches[0]
        if (call['name'] != 'evaluate_candidate' or response.get('metrics') != metrics
                or json.loads(call['arguments'])['strategy_id'] != state['runs'][run_id]['strategy_id']):
            raise ValueError('Session evaluation differs from measured report')
    audit = [json.loads(line) for line in (directory / 'audit.jsonl').read_text().splitlines()]
    for kind, used in state['used'].items():
        reservations = [e['used'] for e in audit if e['operation'] == 'reserve_budget' and e['kind'] == kind]
        if reservations != list(range(1, used + 1)):
            raise ValueError('Budget reservation history differs')
    return {'verified': True, 'episodes_rescored': count, 'evaluations': len(completed),
            'promoted': state['promoted'], 'used': state['used'], 'model_calls': 0,
            'new_simulation_trials': 0}


def source_hash_bytes(raw):
    return hashlib.sha256(raw.decode('utf-8-sig').replace('\r\n', '\n').encode()).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    print(json.dumps(verify(parser.parse_args().directory), indent=2))
