"""One reserved genuine v3 TrueForge session; separate evidence on every turn."""
import argparse
from datetime import datetime, timezone
import json
import re
from pathlib import Path

from agent.configure_trueforge import request
from agent.configure_adaptation_trueforge import CONNECTOR, MODEL, TOOLS
from agent.run_adaptation import collect, write_json
from agent.adaptation_bridge import AdaptationBridge
from evaluation.v3.benchmark import verify


def validate_agent(agent):
    manifest = agent['manifest']
    servers = manifest.get('mcp_servers', [])
    if manifest.get('model', {}).get('name') != MODEL or manifest.get('skills'):
        raise ValueError('Unexpected model or external instruction packs')
    if manifest.get('instructions') != Path(__file__).with_name('adaptation_instructions.md').read_text():
        raise ValueError('Saved instructions differ from the frozen task')
    if len(servers) != 1 or servers[0]['name'] != CONNECTOR or set(servers[0]['enable_tools']) != set(TOOLS):
        raise ValueError('Unexpected tool access')
    config = manifest.get('config', {})
    if any(config.get(k, {}).get('enabled') is not False for k in
           ('sandbox', 'dynamic_sub_agents', 'generative_ui', 'web_search', 'ask_user_questions')):
        raise ValueError('Unexpected external capabilities')
    if not 1 <= config.get('iteration_limit', 0) <= 40:
        raise ValueError('Unexpected model iteration budget')


def start():
    _, lock = verify()
    bridge = AdaptationBridge()
    with bridge.transaction():
        if any(bridge.state['used'].values()):
            raise ValueError('V3 tools already used; inspect evidence rather than creating another session')
        saved = json.loads((bridge.directory / 'trueforge-agent.json').read_text())
        agent_id = saved['data']['id']
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', agent_id):
            raise ValueError('Invalid saved agent ID')
        agent = request('/agents/' + agent_id)['data']
        validate_agent(agent)
        (bridge.directory / 'session-reservation.json').open('x', encoding='utf-8').write(json.dumps({
            'agent_id': agent_id, 'reserved_utc': datetime.now(timezone.utc).isoformat()}) + '\n')
    output = bridge.directory / 'agent_runs' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'agent.json', agent)
    write_json(output / 'benchmark.json', lock)
    session = request('/sessions', {'agent': {'name': agent['name']}})['data']
    run = {'session_id': session['id'], 'agent_id': agent_id, 'benchmark_version': 3,
           'started_utc': datetime.now(timezone.utc).isoformat(), 'status': 'session_created'}
    write_json(output / 'run.json', run)
    turn = request(f"/sessions/{session['id']}/turns", {'stream': False, 'input': [{
        'type': 'user.message', 'content': 'Execute the authorized robotic strategy-adaptation task. Establish the full initial validation baseline, diagnose observable development failures, choose and save an evidence-based recovery strategy, compare identical validation conditions, and call promotion only for genuine measured improvement. Preserve every failure and report actual run IDs. Do not access final-test data or ask for permission to continue.'}]})['data']
    run.update(turn_id=turn['id'], status=turn['state']['status'])
    write_json(output / 'run.json', run)
    print(output)
    print(json.dumps(run, indent=2))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', type=Path)
    args = parser.parse_args()
    print(collect(args.collect) if args.collect else start())
