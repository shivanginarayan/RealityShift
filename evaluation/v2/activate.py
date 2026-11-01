"""Activate v2 exactly once, only from verified stable developer evidence."""
import argparse
import json
from pathlib import Path

from evaluation.benchmark import ROOT, source_hash
from evaluation.heldout import verify_protocol
from evaluation.v2.benchmark import DIRECTORY, SOURCES, read_spec
from evaluation.v2.evidence import verify


AGENT_SOURCES = ['agent/strategy_bridge.py', 'agent/strategy_server.py', 'agent/strategy_instructions.md',
                 'agent/configure_strategy_trueforge.py', 'agent/run_strategy_adaptation.py',
                 'evaluation/v2/activate.py', 'evaluation/v2/evidence.py', 'evaluation/strategy_ablation.py']


def activate(evidence):
    verify_protocol()
    evidence = Path(evidence).resolve()
    if not evidence.is_relative_to(ROOT.resolve()):
        raise ValueError('Stability evidence must be within the project')
    checked = verify(evidence, require_current=True)
    manifest = json.loads((evidence / 'manifest.json').read_text())
    if manifest['spec'] != read_spec() or not checked['stability_passed']:
        raise ValueError('Developer stability gate failed; v2 remains disabled and no budgets are spent')
    gate_path = (evidence / 'stability.json').relative_to(ROOT).as_posix()
    evidence_files = [(evidence / name).relative_to(ROOT).as_posix()
                      for name in ('archive.json', 'manifest.json', 'report.json', 'stability.json')]
    lock = {'benchmark_version': 2, 'gate_path': gate_path, 'gate_sha256': source_hash(ROOT / gate_path),
            'evidence_index_path': (evidence / 'archive.json').relative_to(ROOT).as_posix(),
            'evidence_index_sha256': source_hash(evidence / 'archive.json'),
            'source_sha256': {p: source_hash(ROOT / p) for p in SOURCES + AGENT_SOURCES + evidence_files}}
    with (DIRECTORY / 'frozen.json').open('x', encoding='utf-8') as stream:
        json.dump(lock, stream, indent=2)
    return lock


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    print(json.dumps(activate(parser.parse_args().evidence), indent=2))
