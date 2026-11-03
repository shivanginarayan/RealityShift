"""V3 bounded workflow: full baseline first, opaque cases, immutable decisions."""
from contextlib import contextmanager
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
from uuid import uuid4

from control.adaptation_schema import AdaptationSkill, CHOICES, load, parse, text
from evaluation.benchmark import ROOT, source_hash
from evaluation.v3.benchmark import CORE, AGENT_SOURCES, evaluate, promotion, public_episode, run_episode, spec, verify


LOADED = {p: source_hash(ROOT / p) for p in CORE + AGENT_SOURCES if (ROOT / p).is_file()}


class AdaptationBridge:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.directory = self.root / '.runtime/adaptation-v3'
        if (self.root / '.runtime').is_symlink() or self.directory.is_symlink():
            raise ValueError('Runtime directory must not be a symlink')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        self.limits = {'evaluations': 6, 'trials': 12, 'candidates': 4}
        self.state = self._load()

    def _load(self):
        path = self.directory / 'state.json'
        if path.is_symlink():
            raise ValueError('Invalid state path')
        state = json.loads(path.read_text()) if path.exists() else {
            'protocol': 3, 'used': {k: 0 for k in self.limits}, 'runs': {},
            'baseline_run': None, 'promoted': 'initial'}
        if state.get('protocol') != 3 or set(state.get('used', {})) != set(self.limits):
            raise ValueError('Invalid state; refusing any budget reset')
        if any(type(state['used'][k]) is not int or not 0 <= state['used'][k] <= n for k, n in self.limits.items()):
            raise ValueError('Invalid persistent budgets')
        if not isinstance(state.get('runs'), dict) or state.get('baseline_run') is not None and state['baseline_run'] not in state['runs']:
            raise ValueError('Invalid persisted run receipts')
        return state

    @contextmanager
    def transaction(self, allow_finalized=False):
        with self.lock:
            path = self.directory / 'operation.lock'
            stream = path.open('x', encoding='utf-8')
            try:
                stream.write(datetime.now(timezone.utc).isoformat())
                stream.close()
                self.state = self._load()
                if any(source_hash(ROOT / p) != h for p, h in LOADED.items()):
                    raise ValueError('Loaded sources changed; restart the v3 server')
                if not allow_finalized and (self.directory / 'finalized.json').exists():
                    raise ValueError('Experiment finalized; no further tool operations')
                yield
            finally:
                stream.close()
                path.unlink()

    def audit(self, operation, **payload):
        with (self.directory / 'audit.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), 'operation': operation, **payload}) + '\n')
        temporary = self.directory / 'state.tmp'
        temporary.write_text(json.dumps(self.state, indent=2) + '\n', encoding='utf-8')
        temporary.replace(self.directory / 'state.json')

    def reserve(self, kind):
        if self.state['used'][kind] >= self.limits[kind]:
            raise ValueError(f'{kind} budget exhausted')
        self.state['used'][kind] += 1
        self.audit('reserve_budget', kind=kind, used=self.state['used'][kind])

    def policy_path(self, identifier):
        if identifier == 'initial':
            path = self.root / 'strategies/v3/initial.yaml'
        elif isinstance(identifier, str) and re.fullmatch(r's[0-9]{4}', identifier):
            directory = self.directory / 'strategies'
            if directory.is_symlink():
                raise ValueError('Invalid policy directory')
            path = directory / f'{identifier}.yaml'
        else:
            raise ValueError('Unknown bounded policy identifier')
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(self.root):
            raise ValueError('Policy not found within the allowed directory')
        load(path)
        return path

    def require_baseline(self):
        if not self.state['baseline_run']:
            raise ValueError('Evaluate initial on all validation conditions before saving or evaluating revisions')

    def get_status(self):
        with self.transaction(allow_finalized=True):
            settings, _ = verify()
            if settings['agent_budgets'] != self.limits:
                raise ValueError('Unexpected protocol budgets')
            return {'benchmark_version': 3, 'enabled': True,
                'initial_policy': text(load(self.policy_path('initial'))),
                'recovery_policy_template': text(AdaptationSkill(2, controller='recovery')),
                'choices': CHOICES,
                'strategy_catalog': {
                    'direct': 'Original high-gain position feedback; fast immediate response can oscillate when response changes.',
                    'stabilized': 'Bounded nominal dynamics tracking throughout approach and pushing; slower.',
                    'adaptive': 'Observe early joint response, then use direct or stabilized tracking; latch stabilization after sustained response deterioration or a recovery event.',
                    'controlled_repush': 'Bounded backoff and incremental push after observed stall.',
                    'reposition_correct': 'Lift and choose a nominally reachable goal-directed contact flank after overshoot.',
                    'stabilized_reacquire': 'Stabilized reacquisition, optionally horizontal when the observed path clears the object.',
                    'progress_gated': 'Integrate bounded forward tracking error only after observed productive contact pushing.',
                    'pose_hold': 'Use observed closing motion to brake and hold the observed joint pose near the goal.'},
                'development_cases': [c['id'] for c in settings['splits']['development']],
                'validation_episodes': len(settings['splits']['validation']),
                'workflow': 'Evaluate initial first. Diagnose development failures. Save enum policy, inspect diff, evaluate full validation and promote only measured nonregression.',
                'remaining': {k: n - self.state['used'][k] for k, n in self.limits.items()},
                'baseline_run': self.state['baseline_run'], 'promoted': self.state['promoted']}

    def run_trial(self, strategy_id, condition_id):
        with self.transaction():
            settings, _ = verify()
            conditions = {c['id']: c for c in settings['splits']['development']}
            if condition_id not in conditions:
                raise ValueError('Only listed opaque development cases are available as trials')
            policy = load(self.policy_path(strategy_id))
            self.reserve('trials')
            run_id = uuid4().hex
            try:
                result = run_episode(policy, conditions[condition_id], self.directory / 'trials' / run_id)
                verify()
                response = {'run_id': run_id, **public_episode(result, diagnostics=True)}
                if len(json.dumps(response)) > 14000:
                    raise ValueError('Diagnostic size exceeded bound')
                self.audit('trial_completed', run_id=run_id, strategy_id=strategy_id, condition_id=condition_id)
                return response
            except Exception as error:
                self.audit('trial_failed', run_id=run_id, error=type(error).__name__)
                raise ValueError('Trial failed; reservation retained for developer audit') from None

    def save_candidate_strategy(self, yaml_text, hypothesis):
        with self.transaction():
            verify()
            self.require_baseline()
            policy = parse(yaml_text)
            if policy.version < 2 or not isinstance(hypothesis, str) or not 20 <= len(hypothesis) <= 2000:
                raise ValueError('Use unique version >=2 and a 20-2000 character evidence-based hypothesis')
            identifier = f's{policy.version:04d}'
            directory = self.directory / 'strategies'
            if directory.is_symlink():
                raise ValueError('Invalid policy directory')
            directory.mkdir(exist_ok=True)
            path = directory / f'{identifier}.yaml'
            if path.exists() or path.is_symlink():
                raise ValueError('Saved versions are immutable')
            self.reserve('candidates')
            path.open('x', encoding='utf-8').write(text(policy))
            self.audit('strategy_saved', strategy_id=identifier, hypothesis=hypothesis,
                       policy_sha256=hashlib.sha256(text(policy).encode()).hexdigest())
            return {'strategy_id': identifier, 'policy': text(policy)}

    def get_strategy_diff(self, strategy_id):
        with self.transaction():
            verify()
            before, after = (text(load(self.policy_path(k))) for k in ('initial', strategy_id))
            return {'diff': ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='initial', tofile=strategy_id))}

    def read_report(self, run_id):
        if run_id not in self.state['runs']:
            raise ValueError('Expected a completed full validation evaluation ID')
        receipt = self.state['runs'][run_id]
        path = self.directory / 'evaluations' / run_id / 'report.json'
        if source_hash(path) != receipt['report_sha256']:
            raise ValueError('Evaluation report changed')
        report = json.loads(path.read_text())
        policy = text(load(self.policy_path(receipt['strategy_id'])))
        if hashlib.sha256(policy.encode()).hexdigest() != report['policy_sha256']:
            raise ValueError('Evaluated policy changed')
        return report

    def evaluate_candidate(self, strategy_id):
        with self.transaction():
            verify()
            if strategy_id != 'initial':
                self.require_baseline()
            if strategy_id == 'initial' and self.state['baseline_run']:
                run_id = self.state['baseline_run']
                report = self.read_report(run_id)
                return {'run_id': run_id, 'reused': True, 'metrics': report['aggregate'],
                        'episodes': [public_episode(e) for e in report['episodes']]}
            policy = load(self.policy_path(strategy_id))
            self.reserve('evaluations')
            run_id = uuid4().hex
            try:
                output = self.directory / 'evaluations' / run_id
                report = evaluate(policy, 'validation', output)
                self.state['runs'][run_id] = {'strategy_id': strategy_id, 'aggregate': report['aggregate'],
                    'report_sha256': source_hash(output / 'report.json')}
                if strategy_id == 'initial':
                    self.state['baseline_run'] = run_id
                self.audit('evaluation_completed', run_id=run_id, strategy_id=strategy_id)
                return {'run_id': run_id, 'metrics': report['aggregate'],
                        'episodes': [public_episode(e) for e in report['episodes']]}
            except Exception as error:
                self.audit('evaluation_failed', run_id=run_id, error=type(error).__name__)
                raise ValueError('Full evaluation failed; budget remains reserved') from None

    def promote_strategy(self, baseline_run_id, candidate_run_id):
        with self.transaction():
            verify()
            if baseline_run_id != self.state['baseline_run'] or candidate_run_id == baseline_run_id:
                raise ValueError('Use the genuine initial baseline and a saved candidate full evaluation')
            before, after = self.read_report(baseline_run_id), self.read_report(candidate_run_id)
            accepted = promotion(before, after)
            if accepted:
                self.state['promoted'] = self.state['runs'][candidate_run_id]['strategy_id']
            self.audit('promotion_decision', baseline=baseline_run_id, candidate=candidate_run_id, accepted=accepted)
            return {'accepted': accepted, 'promoted': self.state['promoted'],
                    'criterion': 'strict aggregate improvement with every initial successful validation condition preserved'}
