"""V3 observation-triggered mode latch for changes after initial calibration."""
from collections import deque
import numpy as np

from control.progress_recovery import ProgressRecoveryController
from control.recovery import checked_observation


class ResponseRecoveryController(ProgressRecoveryController):
    def __init__(self, model, strategy=None, **kwargs):
        super().__init__(model, strategy, **kwargs)
        self.stabilization_latched = False
        self.response_errors = deque(maxlen=16)
        self.reference_baseline = None
        self.response_mismatch_streak = 0

    def _begin(self, reason, obs, force_plan=None):
        super()._begin(reason, obs, force_plan)
        if self.strategy.approach == 'adaptive':
            self._latch('recovery_requires_stabilization')

    def _latch(self, reason):
        if not self.stabilization_latched:
            self.stabilization_latched = True
            self._event(reason, self.phase)
        self.stable = True

    def target(self, observation):
        obs = checked_observation(observation)
        previous_target = self.command_target.copy() if self.command_target is not None else None
        previous_stage = self.command_stage
        target, direction = super().target(obs)
        if self.strategy.approach == 'adaptive' and not self.stabilization_latched:
            if previous_target is not None and previous_stage == 'push' and self.command_stage == 'push':
                error = float(np.linalg.norm(obs[14:17] - previous_target))
                # Establish a usable response before detecting deterioration.
                # This does not identify delay or read command queues/forces.
                self.response_errors.append(error)
                if len(self.response_errors) == 16:
                    median = float(np.median(self.response_errors))
                    if median < .04:
                        self.reference_baseline = median if self.reference_baseline is None else min(self.reference_baseline, median)
                bad = self.reference_baseline is not None and error > max(.08, 4 * self.reference_baseline)
                self.response_mismatch_streak = self.response_mismatch_streak + 1 if bad else 0
                if self.response_mismatch_streak >= 3:
                    self._latch('observed_response_deterioration')
            else:
                self.response_errors.clear()
                self.response_mismatch_streak = 0
        if self.stabilization_latched:
            self.stable = True  # Override the old initial-response preference.
        return target, direction

    def diagnostics(self):
        result = super().diagnostics()
        result.update(policy='developer_response_recovery_v3', stabilization_latched=self.stabilization_latched)
        return result
