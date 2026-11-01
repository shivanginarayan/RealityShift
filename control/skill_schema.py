"""Strict data-only skills. Evaluation rules are never skill fields."""
from dataclasses import asdict, dataclass
import math
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ControlSkill:
    name: str
    version: int
    proportional_gain: float
    damping_gain: float
    max_torque: float
    approach_offset: float
    approach_height: float
    push_offset: float
    stop_distance: float
    action_smoothing: float


LIMITS = {
    "proportional_gain": (1, 100), "damping_gain": (0.1, 15),
    "max_torque": (0.1, 2), "approach_offset": (0.05, 0.2),
    "approach_height": (-0.2, -0.08), "push_offset": (0, 0.06),
    "stop_distance": (0.01, 0.08), "action_smoothing": (0.02, 1),
}


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ValueError("Skill keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def parse_skill(text: str) -> ControlSkill:
    if len(text.encode("utf-8")) > 8192:
        raise ValueError("Skill exceeds 8 KiB")
    data = yaml.load(text, Loader=UniqueKeyLoader)
    expected = {"name", "version", "control"}
    if not isinstance(data, dict) or set(data) != expected:
        raise ValueError("Skill must contain exactly name, version and control")
    if data["name"] != "adaptive_pushing":
        raise ValueError("Unsupported skill name")
    version = data["version"]
    if type(version) is not int or not 1 <= version <= 10000:
        raise ValueError("Version must be an integer in [1, 10000]")
    control = data["control"]
    if not isinstance(control, dict) or set(control) != set(LIMITS):
        raise ValueError("Control fields must match the allowlist exactly")
    for key, (low, high) in LIMITS.items():
        value = control[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key} must be finite and in [{low}, {high}]")
    return ControlSkill(data["name"], version, **control)


def load_skill(path: Path) -> ControlSkill:
    path = Path(path)
    if path.stat().st_size > 8192:
        raise ValueError("Skill exceeds 8 KiB")
    return parse_skill(path.read_text(encoding="utf-8"))


def skill_text(skill: ControlSkill) -> str:
    fields = asdict(skill)
    return yaml.safe_dump({"name": fields.pop("name"), "version": fields.pop("version"),
                           "control": fields}, sort_keys=False)


def save_candidate(text: str) -> Path:
    skill = parse_skill(text)
    if skill.version < 2:
        raise ValueError("Candidate versions must be at least 2")
    directory = Path(__file__).parents[1] / "skills" / "versions"
    directory.mkdir(exist_ok=True)
    path = directory / f"v{skill.version:04d}.yaml"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(skill_text(skill))
    return path
