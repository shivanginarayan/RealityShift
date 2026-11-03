"""Publish real v3 traces and independently re-score every archived episode."""
import hashlib
import json
from pathlib import Path
import zipfile

from control.adaptation_schema import parse, text
from evaluation.benchmark import ROOT, source_hash
from evaluation.metrics import aggregate, score_episode
from evaluation.strategy_agent_evidence import projection
from evaluation.v3.benchmark import CORE, AGENT_SOURCES, promotion, spec, verify as verify_protocol


def normalized_hash(raw):
    return hashlib.sha256(raw.decode('utf-8-sig').replace('\r\n', '\n').encode()).hexdigest()


def package(destination):
    verify_protocol()
    root = ROOT / '.runtime/adaptation-v3'
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name in ('state.json', 'audit.jsonl', 'finalized.json', 'final-completion.json',
                 'session-reservation.json', 'trueforge-agent.json'):
        if (root / name).is_file():
            (destination / name).write_bytes((root / name).read_bytes())
    for i, run in enumerate(sorted((root / 'agent_runs').iterdir()), 1):
        receipt = json.loads((run / 'evidence.json').read_text())
        if not receipt['terminal']:
            raise ValueError('Collect terminal agent traces before publication')
        target = destination / f'turn{i}'
        target.mkdir()
        for name in ('agent.json', 'run.json', 'evidence.json', 'supervision.json'):
            if (run / name).is_file():
                (target / name).write_text(json.dumps(projection(json.loads((run / name).read_text())), indent=2) + '\n', encoding='utf-8')
        events = [projection(json.loads(line)) for line in (run / 'events.jsonl').read_text().splitlines()]
        (target / 'events.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in events), encoding='utf-8')
    with zipfile.ZipFile(destination / 'trajectories.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for directory in ('evaluations', 'trials', 'strategies', 'conventional', 'final'):
            for path in sorted((root / directory).rglob('*')):
                if path.is_file():
                    bundle.write(path, path.relative_to(root).as_posix())
        for name in CORE + AGENT_SOURCES + ['evaluation/v3/frozen.json']:
            bundle.write(ROOT / name, 'source/' + name)
    (destination / 'final-summary.json').write_bytes((root / 'final/summary.json').read_bytes())
    (destination / 'search.json').write_bytes((root / 'conventional/search.json').read_bytes())
    index = {'authorship': 'developer primitives; actual agent policy selection recorded in tool events',
             'note': 'reasoning_content removed recursively from public projections. Export receipts retain hashes of original private exports.',
             'sha256': {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        if p.suffix == '.zip' else source_hash(p)
                        for p in sorted(destination.rglob('*')) if p.is_file()}}
    (destination / 'archive.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    return verify(destination)


def verify_development(directory):
    directory = Path(directory)
    index = json.loads((directory / 'archive.json').read_text())
    for name, digest in index['sha256'].items():
        actual = hashlib.sha256((directory / name).read_bytes()).hexdigest() if name.endswith('.zip') else source_hash(directory / name)
        if actual != digest:
            raise ValueError('Development evidence changed')
    report = json.loads((directory / 'report.json').read_text())
    count = 0
    with zipfile.ZipFile(directory / 'trajectories.zip') as bundle:
        archived_spec = json.loads(bundle.read('source/evaluation/v3/spec.json'))
        expected = {c['id'] for c in archived_spec['splits']['development']}
        for name, digest in report['source_sha256'].items():
            if normalized_hash(bundle.read('source/' + name)) != digest:
                raise ValueError('Development measured source differs')
        for label, data in report['variants'].items():
            metrics = []
            if {e['condition_id'] for e in data['episodes']} != expected or len(data['episodes']) != len(expected):
                raise ValueError('Missing development condition')
            for e in data['episodes']:
                raw = bundle.read(f"{label}/{e['condition_id']}/trajectory.jsonl")
                if hashlib.sha256(raw).hexdigest() != e['trajectory_sha256']:
                    raise ValueError('Development trajectory changed')
                scored = score_episode([json.loads(line) for line in raw.splitlines()], archived_spec)
                if any(e[k] != value for k, value in scored.items()):
                    raise ValueError('Development metrics differ')
                metrics.append(scored)
                count += 1
            if aggregate(metrics) != data['aggregate']:
                raise ValueError('Development aggregate differs')
        old = {e['condition_id']: e for e in report['variants']['original']['episodes']}
        new = {e['condition_id']: e for e in report['variants']['developer']['episodes']}
        conditions = archived_spec['splits']['development']
        checks = {'all_eligible': all(e['eligible'] for data in report['variants'].values() for e in data['episodes']),
                  'nominal_nonregression': all(new[c['id']]['success'] for c in conditions
                      if c['delay_steps'] == 0 and old[c['id']]['success']),
                  'unchanged_four_step_delay_conversion': any(not old[c['id']]['success'] and new[c['id']]['success']
                      for c in conditions if c['delay_steps'] == 4 and c['onset_step'] == 0)}
        if report['gate'] != {'passed': all(checks.values()), 'checks': checks}:
            raise ValueError('Developer gate differs from scored outcomes')
    return {'verified': True, 'episodes_rescored': count, 'model_calls': 0}


def verify(directory):
    directory = Path(directory)
    index = json.loads((directory / 'archive.json').read_text())
    for name, digest in index['sha256'].items():
        path = directory / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if name.endswith('.zip') else source_hash(path)
        if actual != digest:
            raise ValueError('Public v3 evidence changed')
    state = json.loads((directory / 'state.json').read_text())
    calls, responses = {}, {}
    for path in directory.glob('turn*/events.jsonl'):
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if projection(row) != row:
                raise ValueError('Private reasoning in public event projection')
            event = row['event']
            for call in event.get('tool_calls', []):
                calls[call['id']] = call['function']
            if event['type'] == 'tool.response':
                try:
                    responses[event['tool_call_id']] = json.loads(event['content'])
                except (ValueError, TypeError):
                    pass
    settings, count, reports = spec(), 0, {}
    with zipfile.ZipFile(directory / 'trajectories.zip') as bundle:
        lock = json.loads(bundle.read('source/evaluation/v3/frozen.json'))
        for name, digest in lock['source_sha256'].items():
            if name in CORE + AGENT_SOURCES and normalized_hash(bundle.read('source/' + name)) != digest:
                raise ValueError('Frozen experiment source differs')
        for name in bundle.namelist():
            if name.endswith('/report.json'):
                report = json.loads(bundle.read(name))
                if report.get('benchmark_version') != 3:
                    continue
                prefix = name.rsplit('/', 1)[0]
                expected = {c['id'] for c in settings['splits'][report['split']]}
                if len(report['episodes']) != len(expected) or {e['condition_id'] for e in report['episodes']} != expected:
                    raise ValueError('Missing or duplicate evaluated conditions')
                measured = []
                for episode in report['episodes']:
                    raw = bundle.read(f"{prefix}/{episode['condition_id']}/trajectory.jsonl")
                    if hashlib.sha256(raw).hexdigest() != episode['trajectory_sha256']:
                        raise ValueError('V3 trajectory differs')
                    scored = score_episode([json.loads(line) for line in raw.splitlines()], settings)
                    if any(episode[k] != value for k, value in scored.items()):
                        raise ValueError('V3 episode score differs')
                    measured.append(scored)
                    count += 1
                if aggregate(measured) != report['aggregate']:
                    raise ValueError('V3 aggregate differs')
                policy = text(parse(bundle.read(prefix + '/policy.yaml').decode('utf-8-sig')))
                if hashlib.sha256(policy.encode()).hexdigest() != report['policy_sha256']:
                    raise ValueError('Evaluated policy differs')
                reports[prefix] = report
                if prefix.startswith('evaluations/'):
                    run_id = prefix.split('/')[1]
                    if normalized_hash(bundle.read(name)) != state['runs'][run_id]['report_sha256']:
                        raise ValueError('Agent report differs from bridge receipt')
            elif name.startswith('trials/') and name.endswith('/trajectory.jsonl'):
                score_episode([json.loads(line) for line in bundle.read(name).splitlines()], settings)
                count += 1
        for run_id, receipt in state['runs'].items():
            report = reports['evaluations/' + run_id]
            matches = [(calls[k], value) for k, value in responses.items()
                       if k in calls and isinstance(value, dict) and value.get('run_id') == run_id and not value.get('reused')]
            if len(matches) != 1:
                raise ValueError('Missing genuine completed evaluation tool response')
            call, response = matches[0]
            if call['name'] != 'evaluate_candidate' or response['metrics'] != report['aggregate'] or json.loads(call['arguments'])['strategy_id'] != receipt['strategy_id']:
                raise ValueError('Agent evaluation tool response differs')
        for call_id, function in calls.items():
            if function['name'] == 'save_candidate_strategy' and call_id in responses and isinstance(responses[call_id], dict) and 'strategy_id' in responses[call_id]:
                args = json.loads(function['arguments'])
                identifier = responses[call_id]['strategy_id']
                if text(parse(args['yaml_text'])) != text(parse(bundle.read(f'strategies/{identifier}.yaml').decode('utf-8-sig'))):
                    raise ValueError('Agent-authored save differs from evaluated policy file')
    audit = [json.loads(line) for line in (directory / 'audit.jsonl').read_text().splitlines()]
    for kind, used in state['used'].items():
        if [e['used'] for e in audit if e['operation'] == 'reserve_budget' and e['kind'] == kind] != list(range(1, used+1)):
            raise ValueError('Budget history differs')
    evaluations = [e for e in audit if e['operation'] == 'evaluation_completed']
    if evaluations[0]['strategy_id'] != 'initial':
        raise ValueError('Full baseline was not evaluated first')
    for decision in [e for e in audit if e['operation'] == 'promotion_decision']:
        before, after = reports['evaluations/' + decision['baseline']], reports['evaluations/' + decision['candidate']]
        if decision['accepted'] != promotion(before, after):
            raise ValueError('Promotion gate result differs')
        if not any(f['name'] == 'promote_strategy' and json.loads(f['arguments']) == {
            'baseline_run_id': decision['baseline'], 'candidate_run_id': decision['candidate']} for f in calls.values()):
            raise ValueError('No actual agent promotion tool call')
    finalized = json.loads((directory / 'finalized.json').read_text())
    for label, policy in finalized['policies'].items():
        if reports['final/' + label]['policy_sha256'] != policy['sha256']:
            raise ValueError('Final policy was not frozen before outcomes')
    from evaluation.v3.final_evaluation import summarize, paired_intervals
    final_summary = json.loads((directory / 'final-summary.json').read_text())
    if final_summary['results'] != {label: summarize(reports['final/' + label]) for label in finalized['policies']}:
        raise ValueError('Final summary differs from scored outcomes')
    for label in ('developer', 'conventional', 'trueforge'):
        if final_summary['paired_vs_original'][label] != paired_intervals(reports['final/original'], reports['final/' + label], settings['splits']['heldout']):
            raise ValueError('Paired uncertainty calculation differs')
    return {'verified': True, 'episodes_rescored': count, 'agent_evaluations': len(state['runs']),
            'conventional_evaluations': sum(k.startswith('conventional/') for k in reports),
            'final_evaluations': sum(k.startswith('final/') for k in reports),
            'promoted': state['promoted'], 'model_calls': 0, 'new_simulation_trials': 0}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--development', action='store_true')
    args = parser.parse_args()
    print(verify_development(args.directory) if args.development else verify(args.directory))
