"""Freeze v3 after development, then execute a predeclared six-evaluation search."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from control.adaptation_schema import load, parse
from evaluation.benchmark import ROOT, source_hash
from evaluation.v2.benchmark import verify_v2
from evaluation.v3.benchmark import CORE, AGENT_SOURCES, DIRECTORY, evaluate, promotion, verify


def publish_development(origin, destination):
    origin, destination = Path(origin), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    report = json.loads((origin / 'report.json').read_text())
    (destination / 'report.json').write_bytes((origin / 'report.json').read_bytes())
    source_bundle = zipfile.ZipFile(origin / 'sources.zip') if (origin / 'sources.zip').is_file() else None
    try:
        with zipfile.ZipFile(destination / 'trajectories.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            paths = list(origin.glob('*/*/trajectory.jsonl'))
            if len(paths) != 42:
                raise ValueError('All 42 development outcomes are required')
            for path in paths:
                bundle.write(path, path.relative_to(origin).as_posix())
            for name, digest in report['source_sha256'].items():
                raw = source_bundle.read(name) if source_bundle else (ROOT / name).read_bytes()
                normalized = raw.decode('utf-8-sig').replace('\r\n', '\n').encode()
                if hashlib.sha256(normalized).hexdigest() != digest:
                    raise ValueError('Development measured source changed before packaging')
                bundle.writestr('source/' + name, raw)
    finally:
        if source_bundle:
            source_bundle.close()
    index = {'episodes': 42, 'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             if p.suffix == '.zip' else source_hash(p) for p in destination.iterdir()}}
    (destination / 'archive.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    return destination


def freeze(development):
    verify_v2()
    development = Path(development).resolve()
    if not development.is_relative_to(ROOT):
        raise ValueError('Gate evidence must be within this project')
    report = json.loads((development / 'report.json').read_text())
    if report['gate']['passed'] is not True:
        raise ValueError('Developer gate did not pass')
    for name, digest in report['source_sha256'].items():
        if source_hash(ROOT / name) != digest:
            raise ValueError('Current source differs from measured development gate')
    files = CORE + AGENT_SOURCES + ['evaluation/v3/development.py',
                                  (development / 'report.json').relative_to(ROOT).as_posix()]
    lock = {'benchmark_version': 3, 'development_gate': str(development.relative_to(ROOT)).replace('\\', '/'),
            'source_sha256': {p: source_hash(ROOT / p) for p in files}}
    (DIRECTORY / 'frozen.json').open('x', encoding='utf-8').write(json.dumps(lock, indent=2) + '\n')
    return lock


def conventional_search():
    settings, _ = verify()
    root = ROOT / '.runtime/adaptation-v3'
    reservation = root / 'conventional-reservation.json'
    reservation.open('x', encoding='utf-8').write(json.dumps(settings['conventional_search'], indent=2) + '\n')
    output = root / 'conventional'
    output.mkdir(exist_ok=False)
    policies = [load(ROOT / 'strategies/v3/initial.yaml')] + [parse(t) for t in settings['conventional_search']['candidate_yaml']]
    if len(policies) != settings['conventional_search']['evaluations']:
        raise ValueError('Predeclared conventional budget mismatch')
    runs, best = [], 0
    for i, policy in enumerate(policies):
        with (output / 'audit.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'operation': 'reserve_evaluation', 'used': i + 1}) + '\n')
        report = evaluate(policy, 'validation', output / f'run{i}')
        runs.append(report)
        if i and promotion(runs[0], report) and report['aggregate']['rank'] > runs[best]['aggregate']['rank']:
            best = i
    result = {'method': 'predeclared developer anchor plus four seeded enum samples, all compared with original',
              'used_evaluations': len(runs), 'limit': 6, 'best_index': best,
              'runs': [{'index': i, 'aggregate': r['aggregate'], 'policy_sha256': r['policy_sha256']} for i, r in enumerate(runs)]}
    (output / 'search.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--freeze', type=Path)
    modes.add_argument('--search', action='store_true')
    args = parser.parse_args()
    print(freeze(args.freeze) if args.freeze else conventional_search())
