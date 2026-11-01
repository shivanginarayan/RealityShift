"""Separate, gated v2 strategy tools and fresh persistent budgets. Never v1 state."""
from contextlib import contextmanager
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
from uuid import uuid4

from control.strategy_schema import OPTIONS, load_strategy, parse_strategy, strategy_text
from evaluation.benchmark import ROOT, source_hash
from evaluation.metrics import can_promote
from evaluation.v2.benchmark import SOURCES, evaluate, read_spec, run_episode, verify_v2


LOADED_SOURCE_HASHES = {name: source_hash(ROOT / name) for name in
                        SOURCES + ['agent/strategy_bridge.py', 'agent/strategy_server.py']}


class StrategyBridge:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.directory = self.root / '.runtime/strategy-v2'
        if (self.root / '.runtime').is_symlink() or self.directory.is_symlink():
            raise ValueError('Invalid v2 runtime directory')
        self.directory.mkdir(parents=True, exist_ok=True)
        if not self.directory.resolve().is_relative_to(self.root):
            raise ValueError('V2 runtime escapes project')
        self.lock = Lock()
        self.limits = {'evaluations': 6, 'trials': 12, 'candidates': 4}
        self.state = self._load()

    def _load(self):
        path = self.directory / 'state.json'
        if path.is_symlink():
            raise ValueError('Invalid state path')
        state = json.loads(path.read_text()) if path.exists() else {
            'protocol': 2, 'used': {k: 0 for k in self.limits}, 'runs': {}, 'promoted': 'initial'}
        if state.get('protocol') != 2 or set(state.get('used', {})) != set(self.limits):
            raise ValueError('Invalid v2 state; refusing budget reset')
        if any(type(state['used'][k]) is not int or not 0 <= state['used'][k] <= v for k, v in self.limits.items()):
            raise ValueError('Invalid v2 budget state')
        return state

    @contextmanager
    def _transaction(self):
        with self.lock:
            path = self.directory / 'operation.lock'
            try:
                stream = path.open('x', encoding='utf-8')
            except FileExistsError:
                raise ValueError('V2 operation already reserved; inspect local lock after a crash') from None
            try:
                stream.write(datetime.now(timezone.utc).isoformat())
                stream.close()
                self.state = self._load()
                if any(source_hash(ROOT / name) != digest for name, digest in LOADED_SOURCE_HASHES.items()):
                    raise ValueError('V2 source changed after import; restart the strategy server')
                yield
            finally:
                stream.close()
                path.unlink()

    def _audit(self, operation, **payload):
        with (self.directory / 'audit.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(),
                                     'operation': operation, **payload}, allow_nan=False) + '\n')
        path = self.directory / 'state.tmp'
        if path.is_symlink():
            raise ValueError('Invalid temporary state path')
        path.write_text(json.dumps(self.state, indent=2), encoding='utf-8')
        path.replace(self.directory / 'state.json')

    def _reserve(self, key):
        if self.state['used'][key] >= self.limits[key]:
            raise ValueError(f'V2 {key} budget exhausted')
        self.state['used'][key] += 1
        self._audit('reserve_budget', kind=key, used=self.state['used'][key])

    def _strategy(self, identifier):
        if identifier == 'initial':
            path = self.root / 'strategies/v2/initial.yaml'
            allowed = self.root / 'strategies/v2'
        elif isinstance(identifier, str) and re.fullmatch(r's[0-9]{4}', identifier):
            path = self.directory / 'strategies' / f'{identifier}.yaml'
            allowed = self.directory / 'strategies'
        else:
            raise ValueError('Unknown strategy identifier')
        if (allowed.is_symlink() or not allowed.resolve().is_relative_to(self.root)
                or path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(allowed.resolve())):
            raise ValueError('Unknown strategy identifier')
        load_strategy(path)
        return path

    def get_status(self):
        with self._transaction():
            try:
                spec, _ = verify_v2()
                enabled, reason = True, None
            except (ValueError, RuntimeError):
                spec = read_spec()
                enabled, reason = False, 'Developer stability gate or v2 freeze verification has not passed'
            if spec['agent_budgets'] != self.limits:
                raise ValueError('Unexpected v2 budgets')
            return {'benchmark_version': 2, 'enabled': enabled, 'blocked_reason': reason,
                    'initial_strategy': strategy_text(load_strategy(self._strategy('initial'))),
                    'strategy_choices': OPTIONS,
                    'cases': {k: {'seeds': v['seeds']} for k, v in spec['cases'].items()},
                    'remaining': {k: v - self.state['used'][k] for k, v in self.limits.items()},
                    'promoted': self.state['promoted']}

    def save_candidate_strategy(self, yaml_text, hypothesis):
        with self._transaction():
            verify_v2()
            skill = parse_strategy(yaml_text)
            if skill.version < 2 or not isinstance(hypothesis, str) or not 20 <= len(hypothesis) <= 2000:
                raise ValueError('Use a unique version >=2 and a 20-2000 character hypothesis')
            identifier = f's{skill.version:04d}'
            directory = self.directory / 'strategies'
            if directory.is_symlink():
                raise ValueError('Invalid strategy directory')
            directory.mkdir(exist_ok=True)
            path = directory / f'{identifier}.yaml'
            if path.exists() or path.is_symlink():
                raise ValueError('Strategy version already exists')
            self._reserve('candidates')
            with path.open('x', encoding='utf-8') as stream:
                stream.write(strategy_text(skill))
            self._audit('strategy_saved', strategy_id=identifier, hypothesis=hypothesis,
                        strategy_sha256=hashlib.sha256(strategy_text(skill).encode()).hexdigest())
            return {'strategy_id': identifier, 'strategy': strategy_text(skill)}

    def get_strategy_diff(self, strategy_id):
        with self._transaction():
            verify_v2()
            before = strategy_text(load_strategy(self._strategy('initial')))
            after = strategy_text(load_strategy(self._strategy(strategy_id)))
            return {'diff': ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                                       fromfile='initial', tofile=strategy_id))}

    @staticmethod
    def _public_episode(result):
        # No scenario labels, intervention details, applied commands or paths.
        return {k: result[k] for k in ('case_id', 'seed', 'eligible', 'violations', 'success', 'score',
                'final_error_xy_m', 'settled_time_fraction', 'mean_squared_torque', 'diagnostics',
                'retries_used', 'strategy_events', 'event_counts', 'stabilized_tracking') if k in result}

    def run_trial(self, strategy_id, case_id, seed):
        with self._transaction():
            spec, _ = verify_v2()
            path = self._strategy(strategy_id)
            if case_id not in spec['cases'] or type(seed) is not int or seed not in spec['cases'][case_id]['seeds']:
                raise ValueError('Only listed development cases/seeds are allowed')
            strategy = load_strategy(path)
            self._reserve('trials')
            run_id = uuid4().hex
            try:
                result = run_episode(strategy, case_id, seed, self.directory / 'trials' / run_id, spec)
                verify_v2()
                public = {'run_id': run_id, **self._public_episode(result)}
                if len(json.dumps(public, indent=2)) > 14000:
                    raise ValueError('Diagnostic output exceeded display bound')
                self._audit('trial_completed', run_id=run_id, strategy_id=strategy_id, case_id=case_id, seed=seed)
                return public
            except Exception:
                self._audit('trial_failed', run_id=run_id)
                raise ValueError('V2 trial failed; inspect developer logs') from None

    def evaluate_candidate(self, strategy_id):
        with self._transaction():
            verify_v2()
            path = self._strategy(strategy_id)
            self._reserve('evaluations')
            run_id = uuid4().hex
            output = self.directory / 'evaluations' / run_id
            try:
                report = evaluate(path, output)
                self.state['runs'][run_id] = {'strategy_id': strategy_id, 'aggregate': report['aggregate'],
                    'strategy_sha256': report['strategy_sha256'], 'report_sha256': source_hash(output / 'report.json'),
                    'case_successes': {case: sum(e['success'] for e in report['episodes'] if e['case_id'] == case)
                                       for case in read_spec()['cases']},
                    'successful_recoveries': {case: sum(e['success'] and any(event['step'] >= read_spec()['probe_step']
                        for event in e.get('strategy_events', [])) for e in report['episodes'] if e['case_id'] == case)
                        for case in ('case_d', 'case_e', 'case_f')}}
                self._audit('evaluation_completed', run_id=run_id, strategy_id=strategy_id)
                # Full compact diagnostics are obtained through bounded trials.
                episodes = [{k: v for k, v in self._public_episode(e).items() if k not in
                             ('diagnostics', 'strategy_events', 'event_counts')} for e in report['episodes']]
                return {'run_id': run_id, 'metrics': report['aggregate'], 'episodes': episodes}
            except Exception:
                self._audit('evaluation_failed', run_id=run_id)
                raise ValueError('V2 evaluation failed; inspect developer logs') from None

    def promote_strategy(self, baseline_run_id, candidate_run_id):
        with self._transaction():
            verify_v2()
            runs = self.state['runs']
            if baseline_run_id not in runs or candidate_run_id not in runs:
                raise ValueError('Both runs must be completed evaluations')
            before, after = runs[baseline_run_id], runs[candidate_run_id]
            if before['strategy_id'] != 'initial' or after['strategy_id'] == 'initial':
                raise ValueError('Compare a saved candidate against the initial strategy')
            for run_id, run in ((baseline_run_id, before), (candidate_run_id, after)):
                report = self.directory / 'evaluations' / run_id / 'report.json'
                canonical = strategy_text(load_strategy(self._strategy(run['strategy_id'])))
                if (source_hash(report) != run['report_sha256']
                        or hashlib.sha256(canonical.encode()).hexdigest() != run['strategy_sha256']):
                    raise ValueError('Evaluated strategy or report changed')
            no_regression = (all(after['case_successes'][case] >= count for case, count in before['case_successes'].items())
                             and all(after['successful_recoveries'][case] >= count
                                     for case, count in before['successful_recoveries'].items()))
            accepted = no_regression and can_promote(before['aggregate'], after['aggregate'])
            if accepted:
                self.state['promoted'] = after['strategy_id']
            self._audit('promotion_decision', baseline=baseline_run_id, candidate=candidate_run_id, accepted=accepted)
            return {'accepted': accepted, 'promoted': self.state['promoted'],
                    'case_and_recovery_nonregression': no_regression}
