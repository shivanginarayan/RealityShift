"""Developer-only shift definitions; do not expose parameters through agent tools."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Scenario:
    name: str
    mass_scale: float = 1.0
    delay_steps: int = 0

    def manifest(self):
        return asdict(self)


SCENARIOS = {
    "nominal": Scenario("nominal"),
    # Stock Pusher's object is extremely light; this scale is a calibration probe.
    "high_mass": Scenario("high_mass", mass_scale=10000.0),
    "actuator_delay": Scenario("actuator_delay", delay_steps=4),
}
