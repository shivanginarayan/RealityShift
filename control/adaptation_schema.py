"""V3 tagged enum-only policies. Original and frozen v2 schemas are unchanged."""
from dataclasses import dataclass
from pathlib import Path

import yaml

from control.strategy_schema import OPTIONS, StrategySkill


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key, value in node.value:
        name = loader.construct_object(key)
        if not isinstance(name, str) or name in result:
            raise ValueError('Only unique string keys are accepted')
        result[name] = loader.construct_object(value)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)
CHOICES = {**OPTIONS, 'tracking_memory': ('off', 'progress_gated'), 'braking': ('off', 'pose_hold')}


@dataclass(frozen=True)
class AdaptationSkill:
    version: int = 1
    controller: str = 'original'
    approach: str = 'adaptive'
    stall: str = 'controlled_repush'
    overshoot: str = 'reposition_correct'
    contact: str = 'stabilized_reacquire'
    tracking_memory: str = 'progress_gated'
    braking: str = 'pose_hold'


def parse(text):
    if not isinstance(text, str) or len(text.encode()) > 4096:
        raise ValueError('Policy must be YAML within 4 KiB')
    try:
        obj = yaml.load(text, Loader=UniqueLoader)
    except (yaml.YAMLError, TypeError, RecursionError) as error:
        raise ValueError('Invalid bounded policy YAML') from error
    if not isinstance(obj, dict) or set(obj) != {'name', 'version', 'policy'} or obj['name'] != 'realityshift_adaptation_v3':
        raise ValueError('Expected exactly name, version and policy')
    version, policy = obj['version'], obj['policy']
    if type(version) is not int or not 1 <= version <= 9999 or not isinstance(policy, dict):
        raise ValueError('Version must be an integer in [1, 9999]')
    controller = policy.get('controller')
    fields = {'controller'} if controller == 'original' else {'controller', *CHOICES}
    if controller not in ('original', 'recovery') or set(policy) != fields:
        raise ValueError('Original has only controller; recovery requires all six enum fields')
    if controller == 'recovery':
        for key, values in CHOICES.items():
            if not isinstance(policy[key], str) or policy[key] not in values:
                raise ValueError(f'Unsupported strategy choice: {key}')
    return AdaptationSkill(version, **policy)


def text(skill):
    policy = {'controller': skill.controller}
    if skill.controller == 'recovery':
        policy.update({k: getattr(skill, k) for k in CHOICES})
    return yaml.safe_dump({'name': 'realityshift_adaptation_v3', 'version': skill.version,
                           'policy': policy}, sort_keys=False)


def load(path):
    return parse(Path(path).read_text(encoding='utf-8-sig'))


def make_controller(model, skill):
    skill = parse(text(skill))
    if skill.controller == 'original':
        from control.controller import PushingController
        return PushingController(model)
    from control.response_recovery import ResponseRecoveryController
    strategies = StrategySkill(1, **{k: getattr(skill, k) for k in OPTIONS})
    return ResponseRecoveryController(model, strategies,
        tracking_memory=skill.tracking_memory == 'progress_gated', braking=skill.braking == 'pose_hold')
