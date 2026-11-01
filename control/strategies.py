"""Distinct bounded recovery maneuvers, selected by observable failure evidence."""
from collections import deque

import mujoco
import numpy as np
from scipy.optimize import least_squares

from agent.strategy_diagnostics import reversals
from control.recovery import RecoveryConfig, RecoveryController, checked_observation
from control.settled_recovery import ConfirmedFailureDetector, SettledRecoveryController
from control.strategy_schema import StrategySkill, parse_strategy, strategy_text


class StrategyFailureDetector(ConfirmedFailureDetector):
    """Detect a near-goal segment crossing even when sampling skips the goal."""

    def reset(self):
        super().reset()
        self.previous_object = None

    def update(self, observation):
        obs = checked_observation(observation)
        point, goal = obs[17:19], obs[20:22]
        previous = self.previous_object
        direction = self.direction.copy() if self.direction is not None else None
        result = super().update(obs)
        self.previous_object = point.copy()
        if previous is not None and direction is not None:
            segment = point - previous
            fraction = np.clip(np.dot(goal - previous, segment) / max(np.dot(segment, segment), 1e-12), 0, 1)
            near_segment = np.linalg.norm(previous + fraction * segment - goal) <= self.config.overshoot_near
            crossed = np.dot(goal - previous, direction) >= 0 and np.dot(goal - point, direction) < -self.config.overshoot_crossing
            if near_segment and crossed and np.linalg.norm(goal - point) > self.tolerance:
                return 'overshoot'
        return result


class StrategyController(SettledRecoveryController):
    def __init__(self, model, strategy=None):
        super().__init__(model)
        self.strategy = parse_strategy(strategy_text(strategy or StrategySkill()))
        self.config = RecoveryConfig(approach_timeout=100, phase_timeout=65, recovery_timeout=180)
        self.detector = StrategyFailureDetector(self.config, self.skill.stop_distance)
        self.stable = self.strategy.approach in ('stabilized', 'adaptive')
        self.probe_responded = False
        self.probe_initial_velocity = None
        self.probe_finished = self.strategy.approach != 'adaptive'
        self.bad_tracking_streak = 0
        self.recent = deque(maxlen=20)
        self.previous_target = None
        self.command_target = None
        self.command_stage = 'approach'
        self.pending_plan = 'reapproach'
        self.snapshot_target = None
        self.repush_error = None
        self.arrival_count = 0
        self.strategy_events = []
        self.push_waypoint = None
        self.nominal_ik_error = None

    def _transition(self, phase):
        super()._transition(phase)
        self.arrival_count = 0

    def _arrived(self, tip, target, threshold=.04):
        self.arrival_count = self.arrival_count + 1 if np.linalg.norm(tip - target) < threshold else 0
        return self.arrival_count >= (3 if self.stable else 1)

    def _begin(self, reason, obs, force_plan=None):
        if self.retries >= 2:
            self._event('retry_budget_exhausted', 'exhausted')
            self._transition('exhausted')
            return
        self.retries += 1
        plan = force_plan or ('repush' if reason == 'stall' and self.strategy.stall == 'controlled_repush'
                  else 'correct' if reason in ('overshoot', 'goal_escape') and self.strategy.overshoot == 'reposition_correct'
                  else 'reapproach')
        if reason in ('lost_contact', 'contact_not_acquired') and self.strategy.contact == 'stabilized_reacquire':
            self.stable = True
        if self.strategy.approach == 'adaptive' and reason in ('approach_timeout', 'phase_timeout'):
            self.stable = True
        self.pending_plan = plan
        self.recovery_started = self.step
        self.recovery_anchor = obs[14:17].copy()
        self.snapshot_target = None
        self.push_waypoint = None
        self.detector.reset()
        phase = 'repush_backoff' if plan == 'repush' else 'stabilize'
        self._event(reason, phase)
        if len(self.strategy_events) < 12:
            self.strategy_events.append({'step': self.step, 'reason': reason, 'strategy': plan,
                                         'stabilized_tracking': self.stable})
        self._transition(phase)
        self.repush_error = float(np.linalg.norm(obs[17:19] - obs[20:22]))

    def _record_target(self, target, stage):
        self.command_stage = stage
        self.command_target = target.copy() if target is not None else None
        self.previous_target = self.command_target
        return target

    def target(self, observation):
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
        # Gentle six-step startup for adaptive mode. Early observed joint
        # response determines whether direct tracking is appropriate. It does
        # not identify latency or query queued/applied commands.
        if not self.probe_finished:
            if self.probe_initial_velocity is None:
                self.probe_initial_velocity = obs[7:14].copy()
            if self.step in (2, 3) and np.linalg.norm(obs[7:14] - self.probe_initial_velocity) > .05:
                self.probe_responded = True
            if self.step == 7:
                self.probe_finished = True
                self.stable = not self.probe_responded
                self._event('early_response_observed' if self.probe_responded else 'early_response_absent', self.phase)
        if self.previous_target is not None:
            self.recent.append((float(np.linalg.norm(tip - self.previous_target)), obs[7:14].copy()))
        if (not self.stable and self.strategy.approach == 'adaptive' and len(self.recent) == 20
                and self.phase in ('approach', 'lower', 'recover_lift', 'reposition', 'correct_lower')):
            distances = [item[0] for item in self.recent]
            bad = (np.median(distances) > .08 and distances[0] - distances[-1] < .025
                   and reversals([item[1] for item in self.recent], .1) > .08)
            self.bad_tracking_streak = self.bad_tracking_streak + 1 if bad else 0
            if self.bad_tracking_streak >= 12:
                self.stable = True
                self._event('observed_tracking_oscillation', self.phase)
        recovery_phases = ('stabilize', 'recover_lift', 'reposition', 'correct_lower', 'repush_backoff', 'repush', 'correct_push')
        age = self.step - self.phase_started
        if self.phase in ('approach', 'lower') and age >= self.config.approach_timeout:
            self._begin('approach_timeout', obs)
        elif self.phase in recovery_phases:
            if self.step - self.recovery_started >= self.config.recovery_timeout:
                self._begin('recovery_timeout', obs, 'reapproach')
            elif age >= self.config.phase_timeout:
                self._begin('phase_timeout', obs, 'reapproach')

        if self.phase in ('push', 'hold', 'correct_push'):
            reason = self.detector.update(obs)
            if reason:
                self._begin(reason, obs)
            elif error <= self.skill.stop_distance:
                if self.phase != 'hold':
                    self.hold_target = tip.copy()
                    self._transition('hold')
            elif self.phase == 'hold':
                self._begin('goal_escape', obs)

        stage = self.phase
        target = None
        if stage == 'exhausted':
            return self._record_target(None, stage), direction
        if stage == 'hold':
            target = self.hold_target.copy()
        elif stage == 'stabilize':
            target = self.recovery_anchor.copy()
            # Wait a fixed bounded interval instead of chasing a moving target.
            if self.step - self.phase_started >= 12:
                self._transition('recover_lift')
        elif stage == 'recover_lift':
            target = self.recovery_anchor.copy()
            target[2] = self.skill.approach_height
            if self._arrived(tip, target):
                self.snapshot_target = raised.copy()  # recompute side AFTER lift
                self._transition('reposition')
        elif stage == 'reposition':
            target = self.snapshot_target.copy()
            if self._arrived(tip, target):
                self._transition('correct_lower')
        elif stage == 'correct_lower':
            target = behind.copy()
            if self._arrived(tip, target, .05):
                self.detector.reset()
                self._transition('correct_push' if self.pending_plan == 'correct' else 'push')
                if self.strategy.approach == 'adaptive':
                    self.stable = True  # bounded contact tracking after reacquisition
        elif stage in ('approach', 'lower'):
            target = raised if stage == 'approach' else behind
            if self._arrived(tip, target, .04 if stage == 'approach' else .05):
                self._transition('lower' if stage == 'approach' else 'push')
                self.detector.reset()
                if stage == 'lower' and self.strategy.approach == 'adaptive':
                    self.stable = True  # responsive free motion, controlled contact motion
        elif stage == 'repush_backoff':
            target = obj.copy()
            target[:2] -= .07 * direction
            if self._arrived(tip, target, .025):
                self._transition('repush')
        else:
            target = obj.copy()
            target[:2] -= (.015 if stage == 'repush' else .035 if stage == 'correct_push' else self.skill.push_offset) * direction
            if stage == 'repush':
                if error <= self.skill.stop_distance or self.repush_error - error >= .012:
                    self._transition('push')
                    self.detector.reset()
                elif self.step - self.phase_started >= 40:
                    self._begin('repush_no_progress', obs, 'reapproach')
                    target = self.recovery_anchor.copy() if self.phase != 'exhausted' else None
                    stage = self.phase
            if stage in ('repush', 'correct_push') and target is not None:
                # Advance a persistent waypoint; resetting it at the actual tip
                # every step makes a slow servo crawl without accumulating push.
                previous = self.push_waypoint if self.push_waypoint is not None else tip
                displacement = target - previous
                waypoint = previous + displacement * min(1., .008 / max(np.linalg.norm(displacement), 1e-9))
                lead = waypoint - tip
                target = tip + lead * min(1., .04 / max(np.linalg.norm(lead), 1e-9))
                self.push_waypoint = target.copy()
        return self._record_target(target, stage), direction

    def _recovery_reference(self, obs, target):
        """Position-first bounded IK for maneuvering around the object.

        A push-entry orientation can conflict with reaching the opposite side.
        Keep the original orientation objective for ordinary initial pushing,
        but do not let it make recovery-position targets unattainable.
        """
        def residual(q):
            self.kinematics.qpos[:7] = q
            mujoco.mj_kinematics(self.model, self.kinematics)
            return np.r_[10 * (self.kinematics.xpos[self.tip_id] - target), .005 * (q - obs[:7])]
        solution = least_squares(residual, obs[:7].clip(self.model.jnt_range[:7, 0] + .001,
                                    self.model.jnt_range[:7, 1] - .001),
                    bounds=(self.model.jnt_range[:7, 0] + .001, self.model.jnt_range[:7, 1] - .001), max_nfev=40)
        self.reference = solution.x

    def action(self, observation):
        obs = checked_observation(observation)
        direct = RecoveryController.action(self, obs)  # one target/phase update
        if self.command_target is not None and self.retries > 0 and self.command_stage not in ('hold', 'stabilize'):
            self._recovery_reference(obs, self.command_target)
            direct = np.clip(self.skill.proportional_gain * (self.reference - obs[:7])
                             - self.skill.damping_gain * obs[7:14], -self.skill.max_torque, self.skill.max_torque)
        self.nominal_ik_error = None
        if self.command_target is not None:
            self.kinematics.qpos[:7] = self.reference
            mujoco.mj_kinematics(self.model, self.kinematics)
            self.nominal_ik_error = float(np.linalg.norm(self.kinematics.xpos[self.tip_id] - self.command_target))
        if not self.stable:
            self.previous_action = direct.copy()
            return direct
        velocity = np.clip(2 * (self.reference - obs[:7]), -.8, .8)
        if self.command_stage in ('stabilize', 'exhausted'):
            velocity[:] = 0
        acceleration = np.clip((velocity - obs[7:14]) / .4, -2., 2.)
        self.dynamics.qpos[:7] = obs[:7]
        self.dynamics.qvel[:] = 0
        self.dynamics.qvel[:7] = obs[7:14]
        mujoco.mj_forward(self.model, self.dynamics)
        mujoco.mj_fullM(self.model, self.dynamics, self.mass_matrix)
        torque = self.mass_matrix[:7, :7] @ acceleration + self.dynamics.qfrc_bias[:7] - self.dynamics.qfrc_passive[:7]
        self.previous_action = np.clip(torque, -self.skill.max_torque, self.skill.max_torque)
        return self.previous_action.copy()

    def diagnostics(self):
        result = super().diagnostics()
        result.update(policy='developer_distinct_strategies_v2', strategy=strategy_text(self.strategy),
                      strategy_events=list(self.strategy_events), stabilized_tracking=self.stable)
        return result
