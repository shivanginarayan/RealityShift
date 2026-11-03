"""A separate saved v3 agent using only the existing NVIDIA provider."""
import json
from pathlib import Path
from urllib.error import HTTPError

from agent.configure_trueforge import request
from evaluation.benchmark import ROOT
from evaluation.v3.benchmark import verify

CONNECTOR = 'realityshift-adaptation-v3'
MODEL = 'nvidia/nemotron-lightning'
TOOLS = ['get_status', 'run_trial', 'save_candidate_strategy', 'get_strategy_diff', 'evaluate_candidate', 'promote_strategy']


def configure():
    verify()
    names = {m['name'] for m in request('/models')['data']}
    if MODEL not in names:
        raise ValueError('Existing NVIDIA model is unavailable; no paid-provider fallback')
    try:
        current = request(f'/settings/mcp-servers/{CONNECTOR}')
        if current['data']['manifest'].get('url') != 'http://127.0.0.1:8767/mcp':
            raise ValueError('Unexpected v3 connector endpoint')
    except HTTPError as error:
        if error.code != 404:
            raise
        request('/settings/mcp-servers', {'manifest': {'type': 'remote', 'name': CONNECTOR,
            'url': 'http://127.0.0.1:8767/mcp', 'description': 'Frozen three-split delay adaptation v3'}})
    if {t['name'] for t in request(f'/mcp-servers/{CONNECTOR}/tools')['data']} != set(TOOLS):
        raise ValueError('Exactly six tools must be discovered')
    record = ROOT / '.runtime/adaptation-v3/trueforge-agent.json'
    if record.exists():
        raise ValueError('Saved v3 agent already recorded; preserve provenance')
    response = request('/agents', {'name': 'realityshift-delay-adapter-v3',
        'description': 'Measured robotic strategy adaptation across paired validation tasks',
        'manifest': {'model': {'name': MODEL}, 'instructions': Path(__file__).with_name('adaptation_instructions.md').read_text(),
            'mcp_servers': [{'name': CONNECTOR, 'enable_tools': TOOLS, 'preload': True, 'require_approval_for_tools': []}],
            'skills': [], 'config': {'iteration_limit': 40, 'sandbox': {'enabled': False},
                'dynamic_sub_agents': {'enabled': False}, 'generative_ui': {'enabled': False},
                'web_search': {'enabled': False}, 'ask_user_questions': {'enabled': False}}}})
    record.open('x', encoding='utf-8').write(json.dumps(response, indent=2) + '\n')
    return record


if __name__ == '__main__':
    print(configure())
