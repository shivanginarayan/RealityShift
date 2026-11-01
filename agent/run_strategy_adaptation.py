"""Launch one gated real TrueForge strategy session, retaining original v1 state."""
import argparse
from datetime import datetime, timezone
import json
import re

from agent.configure_trueforge import request
from agent.configure_strategy_trueforge import CONNECTOR, MODEL, TOOLS
from agent.run_adaptation import collect, write_json
from agent.strategy_bridge import StrategyBridge
from evaluation.benchmark import ROOT
from evaluation.v2.benchmark import verify_v2


def validate_agent(agent):
    manifest = agent['manifest']
    if manifest.get('model', {}).get('name') != MODEL or manifest.get('skills'):
        raise ValueError('Unexpected v2 model or external instruction packs')
    servers = manifest.get('mcp_servers', [])
    if len(servers) != 1 or servers[0]['name'] != CONNECTOR or set(servers[0]['enable_tools']) != set(TOOLS):
        raise ValueError('Unexpected strategy connector/tool permissions')
    config = manifest.get('config', {})
    for field in ('sandbox', 'dynamic_sub_agents', 'web_search', 'generative_ui', 'ask_user_questions'):
        if config.get(field, {}).get('enabled') is not False:
            raise ValueError('Unexpected v2 agent capability')
    if not 1 <= config.get('iteration_limit', 0) <= 40:
        raise ValueError('Invalid iteration limit')


def start():
    _, lock = verify_v2()
    bridge = StrategyBridge()
    with bridge._transaction():
        if any(bridge.state['used'].values()):
            raise ValueError('V2 tools already used; inspect provenance instead of launching another session')
        directory = bridge.directory
        saved = json.loads((directory / 'trueforge-agent.json').read_text())
        agent_id = saved['data']['id']
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', agent_id):
            raise ValueError('Invalid agent ID')
        # Durable reservation prevents accidental duplicate model sessions.
        with (directory / 'session-reservation.json').open('x', encoding='utf-8') as stream:
            json.dump({'reserved_utc': datetime.now(timezone.utc).isoformat(), 'agent_id': agent_id}, stream)
    agent = request(f'/agents/{agent_id}')['data']
    validate_agent(agent)
    output = directory / 'agent_runs' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'agent.json', agent)
    write_json(output / 'benchmark.json', lock)
    session = request('/sessions', {'agent': {'name': agent['name']}})['data']
    run = {'session_id': session['id'], 'agent_id': agent_id, 'benchmark_version': 2,
           'started_utc': datetime.now(timezone.utc).isoformat(), 'status': 'session_created'}
    write_json(output / 'run.json', run)
    turn = request(f"/sessions/{session['id']}/turns", {'stream': False, 'input': [{
        'type': 'user.message', 'content': 'Follow your v2 strategy instructions. Establish a measured initial baseline, diagnose failing opaque development cases, save/evaluate strategy revisions and promote only genuine measured improvement. Preserve all failed results and distinguish tracking from actual recovery.'}]})['data']
    run.update(turn_id=turn['id'], status=turn['state']['status'])
    write_json(output / 'run.json', run)
    return output, run


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect')
    args = parser.parse_args()
    print(collect(args.collect) if args.collect else start())
