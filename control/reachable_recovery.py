"""Reachability-checked recovery planning, separate from archived strategy code."""
from dataclasses import dataclass

import mujoco
import numpy as np
from scipy.optimize import least_squares

from control.recovery import checked_observation
from control.strategies import StrategyController


@dataclass
class ContactPlan:
    raised: np.ndarray
    contact: np.ndarray
    raised_joints: np.ndarray
    contact_joints: np.ndarray
    object_xy: np.ndarray
    angle: float
    offset: float
    max_residual: float


class ReachableStrategyController(StrategyController):
    """Choose a reachable goal-directed flank instead of repeating infeasible IK.

    All planning uses the independent nominal model and observed robot/object/
    goal positions. Candidate force directions stay within 60 degrees of the
    goal direction; an unreachable opposite side is never replaced by a push
    away from the goal. This bounded local search is not a global IK proof.
    """

    def __init__(self, model, strategy=None):
        super().__init__(model, strategy)
        self.plan = None
        self.plan_attempts = 0
        self.replans = 0
        self.previous_object = None
        self.current_observation = None
        self.contact_was_observed = False
        self.planning_events = []
        self.flank_waypoint = None
        self.table_id = model.geom('table').id
        excluded_bodies = {0, model.body('object').id, model.body('goal').id}
        self.robot_geoms = np.array([i for i in range(model.ngeom)
            if model.geom_bodyid[i] not in excluded_bodies
            and model.geom_type[i] in (mujoco.mjtGeom.mjGEOM_SPHERE, mujoco.mjtGeom.mjGEOM_CAPSULE)
            and ((model.geom_contype[i] & model.geom_conaffinity[self.table_id])
                 or (model.geom_contype[self.table_id] & model.geom_conaffinity[i]))])

    def table_clearances(self):
        """Analytic nominal sphere/capsule clearance; no contact forces read."""
        data, model = self.kinematics, self.model
        normal = data.geom_xmat[self.table_id].reshape(3, 3)[:, 2]
        positions = data.geom_xpos[self.robot_geoms] - data.geom_xpos[self.table_id]
        support = model.geom_size[self.robot_geoms, 0].copy()
        for index, geom in enumerate(self.robot_geoms):
            if model.geom_type[geom] == mujoco.mjtGeom.mjGEOM_CAPSULE:
                axis = data.geom_xmat[geom].reshape(3, 3)[:, 2]
                support[index] += model.geom_size[geom, 1] * abs(np.dot(axis, normal))
        return positions @ normal - support

    def _solve_position(self, target, obs, force=None, seed=None):
        data = self.kinematics
        def residual(q):
            data.qpos[:7] = q
            mujoco.mj_kinematics(self.model, data)
            pose = 10 * (data.xpos[self.tip_id] - target)
            if force is not None:
                rotation = data.xmat[self.tip_id].reshape(3, 3)
                # Preserve either valid yaw branch: the original pusher also
                # permits the palm X axis parallel OR antiparallel to motion.
                # Fixing a single full yaw pose excludes otherwise valid pushes.
                pose = np.r_[pose, .5 * np.dot(rotation[:, 1], np.r_[force, 0.]),
                             .5 * rotation[2, 1]]
            # A position-feasible fingertip can still put the palm/forearm
            # through the table. Include all nominal robot capsule/sphere
            # supports and reject penetrations at the final candidate check.
            return np.r_[pose, 10 * np.minimum(self.table_clearances() + .001, 0), .005 * (q - obs[:7])]
        bounds = self.model.jnt_range[:7]
        start = obs[:7] if seed is None else seed
        result = least_squares(residual, start.clip(bounds[:, 0] + .001, bounds[:, 1] - .001),
                               bounds=(bounds[:, 0] + .001, bounds[:, 1] - .001), max_nfev=40)
        data.qpos[:7] = result.x
        mujoco.mj_kinematics(self.model, data)
        return result.x.copy(), float(np.linalg.norm(data.xpos[self.tip_id] - target))

    def choose_contact_plan(self, observation):
        obs = checked_observation(observation)
        obj, goal = obs[17:20], obs[20:23]
        # Place only the independent nominal object's geometry from observed XY.
        self.kinematics.qpos[8] = obj[0] - self.model.body('object').pos[0]
        self.kinematics.qpos[7] = obj[1] - self.model.body('object').pos[1]
        direction = goal[:2] - obj[:2]
        direction /= max(np.linalg.norm(direction), 1e-9)
        self.plan_attempts = 0
        for angle in (0., np.pi / 6, -np.pi / 6, np.pi / 3, -np.pi / 3):
            rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
            force = rotation @ direction
            for offset, height in ((o, h) for h in (0., .04, .08) for o in (.09, .06, .035)):
                self.plan_attempts += 1
                contact = obj.copy()
                contact[:2] -= offset * force
                contact[2] += height
                raised = contact.copy()
                raised[2] = max(self.skill.approach_height, contact[2] + .06)
                high_q, high_error = self._solve_position(raised, obs, force)
                if high_error > .025 or np.min(self.table_clearances()) < -.002:
                    continue
                low_q, low_error = self._solve_position(contact, obs, force, seed=high_q)
                self.kinematics.qpos[:7] = low_q
                mujoco.mj_kinematics(self.model, self.kinematics)
                axis = self.kinematics.xmat[self.tip_id].reshape(3, 3)[:, 1]
                contact_orientation_valid = abs(np.dot(axis, np.r_[force, 0.])) <= .3 and abs(axis[2]) <= .3
                object_geom = int(self.model.body_geomadr[self.model.body('object').id])
                contact_gap = min(mujoco.mj_geomDistance(self.model, self.kinematics, int(g), object_geom, 1., None)
                                  for g in self.robot_geoms)
                if (low_error <= .025 and contact_orientation_valid
                        and -.02 <= contact_gap <= .03 and np.min(self.table_clearances()) >= -.002):
                    return ContactPlan(raised, contact, high_q, low_q, obj[:2].copy(),
                                       angle, offset, max(high_error, low_error))
        return None

    def _begin(self, reason, obs, force_plan=None):
        self.plan = None
        self.replans = 0
        self.flank_waypoint = None
        super()._begin(reason, obs, force_plan)
        if (reason == 'lost_contact' and self.phase != 'exhausted'
                and self.strategy.contact == 'stabilized_reacquire'):
            plan = self.choose_contact_plan(obs)
            if plan is not None and self.clear_horizontal_path(obs[14:17], plan.contact, obs[17:20]):
                self.plan = plan
                self._transition('reacquire')
                self.strategy_events[-1]['strategy'] = 'horizontal_reacquire'

    @staticmethod
    def clear_horizontal_path(tip, target, obj):
        delta = target[:2] - tip[:2]
        t = np.clip(np.dot(obj[:2] - tip[:2], delta) / max(np.dot(delta, delta), 1e-12), 0, 1)
        return abs(tip[2] - target[2]) < .04 and np.linalg.norm(tip[:2] + t * delta - obj[:2]) >= .055

    def _prepare_plan(self):
        self.plan = self.choose_contact_plan(self.current_observation)
        if self.plan is None:
            self._event('no_feasible_contact_plan', 'exhausted')
            super()._transition('exhausted')
            return False
        self.snapshot_target = self.plan.raised.copy()
        if len(self.planning_events) < 6:
            self.planning_events.append({'step': self.step, 'candidates_tested': self.plan_attempts,
                                        'angle_degrees': round(float(np.degrees(self.plan.angle)), 3),
                                        'offset_m': self.plan.offset, 'nominal_residual_m': self.plan.max_residual})
        return True

    def _transition(self, phase):
        if phase == 'reposition' and self.current_observation is not None:
            if not self._prepare_plan():
                return
        super()._transition(phase)

    def _arrived(self, tip, target, threshold=.04):
        if self.phase == 'correct_lower' and self.plan is not None:
            target, threshold = self.plan.contact, .04
        return super()._arrived(tip, target, threshold)

    def target(self, observation):
        obs = checked_observation(observation)
        self.current_observation = obs.copy()
        old_phase = self.phase
        gap = float(np.linalg.norm(obs[14:17] - obs[17:20]))
        discontinuity = (self.previous_object is not None and self.contact_was_observed
                         and np.linalg.norm(obs[17:19] - self.previous_object) > .08 and gap > .10)
        self.previous_object = obs[17:19].copy()
        if old_phase in ('push', 'hold', 'repush') and gap <= .065:
            self.contact_was_observed = True
        if old_phase == 'reacquire':
            self.step += 1
            direction = obs[20:22] - obs[17:19]
            direction /= max(np.linalg.norm(direction), 1e-9)
            if (self.step - self.phase_started >= self.config.phase_timeout
                    or self.step - self.recovery_started >= self.config.recovery_timeout):
                self._begin('phase_timeout', obs, 'reapproach')
                target = self.recovery_anchor.copy() if self.phase != 'exhausted' else None
                return self._record_target(target, self.phase), direction
            target = self.plan.contact.copy()
            if self._arrived(obs[14:17], target, .04):
                self.detector.reset()
                self._transition('push')
                self.stable = not self.probe_responded
            return self._record_target(target, 'reacquire'), direction
        target, direction = super().target(obs)
        if discontinuity and self.phase in ('push', 'hold'):
            # Strong geometric separation is actionable immediately. A remote
            # object jump must not spend another full stall window unclassified.
            self._begin('lost_contact', obs)
            target = self.recovery_anchor.copy() if self.phase != 'exhausted' else None
            if self.phase == 'reacquire':
                target = self.plan.contact.copy()
            self._record_target(target, self.phase)
        if self.phase == 'exhausted':
            return self._record_target(None, 'exhausted'), direction
        if self.command_stage == 'correct_lower' and self.plan is not None:
            if np.linalg.norm(obs[17:19] - self.plan.object_xy) > .04 and self.replans < 1:
                self.replans += 1
                self._transition('reposition')
                if self.phase == 'exhausted':
                    return self._record_target(None, 'exhausted'), direction
                target = self.plan.raised.copy()
                return self._record_target(target, 'reposition'), direction
            target = self.plan.contact.copy()
            self._record_target(target, 'correct_lower')
        if self.phase == 'push' and self.strategy.approach == 'adaptive' and self.probe_responded:
            # Retain the verified responsive nominal pushing law; stabilization
            # is for weak response/reacquisition, not a universal slowdown.
            self.stable = False
        if self.command_stage in ('push', 'correct_push') and self.plan is not None:
            angle = self.plan.angle
            rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
            direction = rotation @ direction
            target = obs[17:20].copy()
            target[2] = self.plan.contact[2]
            target[:2] -= (.035 if self.command_stage == 'correct_push' else self.skill.push_offset) * direction
            if self.command_stage == 'correct_push':
                previous = self.flank_waypoint if self.flank_waypoint is not None else obs[14:17]
                step = target - previous
                target = previous + step * min(1., .008 / max(np.linalg.norm(step), 1e-9))
                lead = target - obs[14:17]
                target = obs[14:17] + lead * min(1., .04 / max(np.linalg.norm(lead), 1e-9))
                self.flank_waypoint = target.copy()
            self._record_target(target, self.command_stage)
        return target, direction

    def _recovery_reference(self, obs, target):
        if self.plan is not None:
            for point, joints in ((self.plan.raised, self.plan.raised_joints),
                                  (self.plan.contact, self.plan.contact_joints)):
                if np.linalg.norm(target - point) < 1e-8:
                    self.reference = joints.copy()
                    return
        if self.command_stage in ('push', 'repush', 'correct_push'):
            if self.plan is not None:
                direction = obs[20:22] - obs[17:19]
                direction /= max(np.linalg.norm(direction), 1e-9)
                a = self.plan.angle
                direction = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]) @ direction
                self.reference, _ = self._solve_position(target, obs, direction, seed=self.reference)
            return  # preserve orientation-aware contact pose computed by base
        super()._recovery_reference(obs, target)

    def diagnostics(self):
        result = super().diagnostics()
        result.update(policy='developer_reachable_recovery', planning_events=list(self.planning_events))
        return result
