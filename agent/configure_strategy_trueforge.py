"""Configure a NEW TrueForge v2 connector/agent only after stability activation."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError

from agent.configure_trueforge import request
from evaluation.benchmark import ROOT
from evaluation.v2.benchmark import verify_v2


CONNECTOR = 'realityshift-strategy-v2'
TOOLS = ['get_status', 'run_trial', 'save_candidate_strategy', 'get_strategy_diff',
         'evaluate_candidate', 'promote_strategy']
MODEL = 'nvidia/nemotron-lightning'


def configure(model=MODEL):
    verify_v2()  # Must precede every service request, including /models.
    if model != MODEL:
        raise ValueError('Use the existing configured NVIDIA model; no paid-provider fallback')
    try:
        current = request(f'/settings/mcp-servers/{CONNECTOR}')
        if current['data']['manifest'].get('url') != 'http://127.0.0.1:8766/mcp':
            raise ValueError('Existing v2 connector has an unexpected endpoint')
    except HTTPError as error:
        if error.code != 404:
            raise
        request('/settings/mcp-servers', {'manifest': {'type': 'remote', 'name': CONNECTOR,
                'url': 'http://127.0.0.1:8766/mcp', 'description': 'Gated recovery-strategy benchmark v2'}})
    discovered = request(f'/mcp-servers/{CONNECTOR}/tools')['data']
    if {t['name'] for t in discovered} != set(TOOLS):
        raise ValueError('V2 connector must expose exactly the six strategy tools')
    body = {'name': 'realityshift-strategy-adapter-v2', 'description': 'Measured recovery strategy selection, v2',
            'manifest': {'model': {'name': model},
                'instructions': Path(__file__).with_name('strategy_instructions.md').read_text(),
                'mcp_servers': [{'name': CONNECTOR, 'enable_tools': TOOLS,
                                 'preload': True, 'require_approval_for_tools': []}],
                'skills': [], 'config': {'iteration_limit': 40, 'sandbox': {'enabled': False},
                    'dynamic_sub_agents': {'enabled': False}, 'generative_ui': {'enabled': False},
                    'web_search': {'enabled': False}, 'ask_user_questions': {'enabled': False}}}}
    record = ROOT / '.runtime/strategy-v2/trueforge-agent.json'
    record.parent.mkdir(parents=True, exist_ok=True)
    if record.exists():
        raise ValueError('V2 saved agent already recorded; do not silently overwrite provenance')
    response = request('/agents', body)
    with record.open('x', encoding='utf-8') as stream:
        json.dump(response, stream, indent=2)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default=MODEL)
    print(configure(parser.parse_args().model))
