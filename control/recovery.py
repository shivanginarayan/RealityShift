"""Developer-authored recovery v2; opt-in, independent of frozen controller v1.

Contact is a geometric inference, not a simulator contact sensor. No shifted
model, applied command, mass, delay or reward is consulted by the policy.
"""
from collections import Counter, deque
from dataclasses import asdict, dataclass

import mujoco
import numpy as np
from scipy.optimize import least_squares

from control.controller import PushingController


@dataclass(frozen=True)
class RecoveryConfig:
    """Fixed developer policy, deliberately not an agent-editable v1 skill."""

    window: int = 24
    min_progress: float = .008
    max_stall_motion: float = .02
    contact_gap: float = .13
    contact_patience: int = 8
    overshoot_near: float = .065
    overshoot_crossing: float = .015
    overshoot_growth: float = .012
    max_retries: int = 2
    phase_timeout: int = 35
    recovery_timeout: int = 100
    approach_timeout: int = 65
    brake_steps: int = 8

    def __post_init__(self):
        for name in ("window", "contact_patience", "max_retries", "phase_timeout",
                     "recovery_timeout", "approach_timeout", "brake_steps"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 300:
                raise ValueError(f"Invalid recovery bound: {name}")
        for name in ("min_progress", "max_stall_motion", "contact_gap",
                     "overshoot_near", "overshoot_crossing", "overshoot_growth"):
            value = getattr(self, name)
            if not np.isfinite(value) or not 0 < value <= .5:
                raise ValueError(f"Invalid recovery threshold: {name}")


def checked_observation(observation):
    obs = np.asarray(observation, dtype=float)
    if obs.shape != (23,) or not np.isfinite(obs).all():
        raise ValueError("Recovery requires a finite 23-value observation")
    return obs


class FailureDetector:
    """Debounced observation-only hypotheses, evaluated during pushing.

    Overshoot requires crossing the goal plane along the push-entry direction,
    after reaching the near-goal zone, followed by increasing error. Stall uses
    net goal progress AND object displacement over a window. Lost contact uses
    persistent fingertip/object separation AND lack of progress.
    """

    def __init__(self, config=None, tolerance=.05):
        self.config = config or RecoveryConfig()
        self.tolerance = tolerance
        self.reset()

    def reset(self):
        self.history = deque(maxlen=self.config.window)
        self.direction = None
        self.best_error = float("inf")
        self.separated = 0
        self.contact_seen = False
        self.samples = 0

    def update(self, observation):
        obs = checked_observation(observation)
        tip, obj, goal = obs[14:17], obs[17:20], obs[20:23]
        delta = goal[:2] - obj[:2]
        error = float(np.linalg.norm(delta))
        if self.direction is None:
            self.direction = delta / max(error, 1e-9)
        self.best_error = min(self.best_error, error)
        gap = float(np.linalg.norm(tip - obj))
        self.samples += 1
        # Establish a proximity observation before claiming contact was LOST.
        # A separated fingertip on push entry is normal during acquisition.
        if not self.contact_seen and gap <= self.config.contact_gap / 2:
            self.contact_seen = True
            # Stall evidence must span established proximity, not the earlier
            # acquisition interval during which no object motion is expected.
            self.history.clear()
        self.separated = self.separated + 1 if gap > self.config.contact_gap else 0
        self.history.append((obj[:2].copy(), error))
        progress = self.history[0][1] - error
        motion = float(np.linalg.norm(obj[:2] - self.history[0][0]))
        if error <= self.tolerance:
            return None
        if (self.best_error <= self.config.overshoot_near
                and float(np.dot(delta, self.direction)) < -self.config.overshoot_crossing
                and error - self.best_error >= self.config.overshoot_growth):
            return "overshoot"
        if (self.contact_seen and self.separated >= self.config.contact_patience
                and progress < self.config.min_progress):
            return "lost_contact"
        if (not self.contact_seen and self.samples >= 2 * self.config.window
                and progress < self.config.min_progress):
            return "contact_not_acquired"
        if (self.contact_seen and len(self.history) == self.config.window
                and progress < self.config.min_progress
                and motion < self.config.max_stall_motion):
            return "stall"
        return None


class RecoveryController(PushingController):
    """Lift, reapproach, lower and retry, with bounded attempts and phase times.

    Reuses the v1 skill gains and nominal IK model. The v1 source is unchanged;
    the IK calculation below mirrors its tracking law for explicit new targets.
    """

    def __init__(self, model, skill=None, config=None):
        super().__init__(model, skill)
        self.config = config or RecoveryConfig()
        self.detector = FailureDetector(self.config, self.skill.stop_distance)
        self.retries = 0
        self.step = 0
        self.phase_started = 0
        self.recovery_started = None
        self.events = []
        self.event_counts = Counter()
        self.recovery_anchor = None
        self.hold_target = None

    def _event(self, reason, destination):
        self.event_counts[reason] += 1
        # Bound diagnostic size independently of episode duration.
        if len(self.events) < 16:
            self.events.append({"step": self.step, "reason": reason,
                                "from": self.phase, "to": destination})

    def _transition(self, phase):
        self.phase = phase
        self.phase_started = self.step

    def _recover(self, reason, obs):
        if self.retries >= self.config.max_retries:
            self._event("retry_budget_exhausted", "exhausted")
            self._transition("exhausted")
            return
        self.retries += 1
        self._event(reason, "recover_brake")
        self.recovery_started = self.step
        self.recovery_anchor = obs[14:17].copy()
        self.detector.reset()
        self._transition("recover_brake")

    def target(self, observation):
        """Advance policy once per observation; exposed for deterministic tests."""
        obs = checked_observation(observation)
        self.step += 1
        tip, obj, goal = obs[14:17], obs[17:20], obs[20:23]
        delta = goal[:2] - obj[:2]
        error = float(np.linalg.norm(delta))
        direction = delta / max(error, 1e-9)
        behind = obj.copy()
        behind[:2] -= self.skill.approach_offset * direction
        raised = behind.copy()
        raised[2] = self.skill.approach_height
        age = self.step - self.phase_started

        if self.phase.startswith("recover_"):
            if self.step - self.recovery_started >= self.config.recovery_timeout:
                self._recover("recovery_timeout", obs)
            elif age >= self.config.phase_timeout:
                self._recover("phase_timeout", obs)
        elif self.phase in ("approach", "lower") and age >= self.config.approach_timeout:
            self._recover("approach_timeout", obs)

        if self.phase in ("push", "hold"):
            reason = self.detector.update(obs)
            if reason:
                self._recover(reason, obs)
            elif error <= self.skill.stop_distance:
                if self.phase != "hold":
                    self.hold_target = tip.copy()
                    self._transition("hold")
            elif self.phase == "hold":
                self._recover("goal_escape", obs)

        if self.phase == "exhausted":
            return None, direction
        if self.phase == "hold":
            return self.hold_target.copy(), direction
        if self.phase == "recover_brake":
            target = self.recovery_anchor.copy()
            if self.step - self.phase_started >= self.config.brake_steps:
                self._transition("recover_lift")
            return target, direction
        if self.phase == "recover_lift":
            target = self.recovery_anchor.copy()
            target[2] = self.skill.approach_height
            if np.linalg.norm(tip - target) < .04:
                self._transition("recover_reapproach")
            return target, direction
        if self.phase in ("approach", "recover_reapproach"):
            if np.linalg.norm(tip - raised) < .04:
                self._transition("lower" if self.phase == "approach" else "recover_lower")
            return raised, direction
        if self.phase in ("lower", "recover_lower"):
            if np.linalg.norm(tip - behind) < .05:
                self._transition("push")
                self.detector.reset()
            return behind, direction
        target = obj.copy()
        target[:2] -= self.skill.push_offset * direction
        return target, direction

    def action(self, observation):
        obs = checked_observation(observation)
        target, direction = self.target(obs)
        if target is None:
            # Bounded damping after exhaustion; no more push/retry commands.
            self.previous_action = np.clip(-self.skill.damping_gain * obs[7:14],
                                           -self.skill.max_torque, self.skill.max_torque)
            return self.previous_action.copy()

        def residual(q):
            self.kinematics.qpos[:7] = q
            mujoco.mj_kinematics(self.model, self.kinematics)
            rotation = self.kinematics.xmat[self.tip_id].reshape(3, 3)
            return np.concatenate((10 * (self.kinematics.xpos[self.tip_id] - target),
                                   [.5 * np.dot(rotation[:, 1], np.r_[direction, 0.])],
                                   [.5 * rotation[2, 1]], .005 * (q - self.reference)))

        solution = least_squares(residual, self.reference,
                                 bounds=(self.model.jnt_range[:7, 0] + .001,
                                         self.model.jnt_range[:7, 1] - .001), max_nfev=60)
        self.reference = solution.x
        raw = np.clip(self.skill.proportional_gain * (self.reference - obs[:7])
                      - self.skill.damping_gain * obs[7:14],
                      -self.skill.max_torque, self.skill.max_torque)
        alpha = self.skill.action_smoothing
        self.previous_action = alpha * raw + (1 - alpha) * self.previous_action
        return self.previous_action.copy()

    def diagnostics(self):
        return {"policy": "developer_recovery_v2", "phase": self.phase,
                "retries_used": self.retries, "retry_limit": self.config.max_retries,
                "event_counts": dict(self.event_counts), "events": list(self.events),
                "config": asdict(self.config),
                "interpretation": "Observation-based hypotheses; contact is inferred geometrically."}
