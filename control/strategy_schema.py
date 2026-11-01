"""Strict enum-only strategy skills, separate from the immutable v1 gain schema."""
from dataclasses import dataclass, asdict
from pathlib import Path

import yaml

from control.skill_schema import UniqueKeyLoader


OPTIONS = {'approach': ('direct', 'stabilized', 'adaptive'),
           'stall': ('reapproach', 'controlled_repush'),
           'overshoot': ('reapproach', 'reposition_correct'),
           'contact': ('reapproach', 'stabilized_reacquire')}


@dataclass(frozen=True)
class StrategySkill:
    version: int = 1
    approach: str = 'adaptive'
    stall: str = 'controlled_repush'
    overshoot: str = 'reposition_correct'
    contact: str = 'stabilized_reacquire'


def parse_strategy(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 4096:
        raise ValueError('Strategy must be text at most 4 KiB')
    try:
        data = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise ValueError('Invalid strategy YAML') from error
    if not isinstance(data, dict) or set(data) != {'name', 'version', 'strategies'}:
        raise ValueError('Expected exactly name, version, strategies')
    if data['name'] != 'recovery_strategy_v2' or type(data['version']) is not int or not 1 <= data['version'] <= 9999:
        raise ValueError('Invalid strategy name/version')
    choices = data['strategies']
    if not isinstance(choices, dict) or set(choices) != set(OPTIONS):
        raise ValueError('Strategy fields must match allowlist')
    for key, value in choices.items():
        if type(value) is not str or value not in OPTIONS[key]:
            raise ValueError(f'Invalid strategy selection: {key}')
    return StrategySkill(data['version'], **choices)


def strategy_text(skill):
    fields = asdict(skill)
    version = fields.pop('version')
    return yaml.safe_dump({'name': 'recovery_strategy_v2', 'version': version, 'strategies': fields}, sort_keys=False)


def load_strategy(path):
    path = Path(path)
    if path.stat().st_size > 4096:
        raise ValueError('Strategy too large')
    return parse_strategy(path.read_text(encoding='utf-8'))
