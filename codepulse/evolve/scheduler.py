"""Learning-rate-style schedulers for SkillOpt self-evolution.

Controls how aggressively prompt edits are applied per epoch. Inspired by
learning rate schedules in optimisation: high schedule values early for
exploration, decaying over time for refinement.

Schedulers produce a ``scale`` in [0, 1] that multiplies the number of
edits or the confidence threshold during the backward pass.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class Scheduler(ABC):
    """Base class for SkillOpt learning rate schedulers."""

    @abstractmethod
    def scale(self, epoch: int, total_epochs: int, **kwargs: float) -> float:
        """Return a scale factor for the current epoch.

        Args:
            epoch: Current epoch index (0-based).
            total_epochs: Total number of epochs planned.

        Returns:
            Scale factor in [0, 1].
        """
        ...


@dataclass
class CosineDecayScheduler(Scheduler):
    """Cosine annealing scheduler with optional warmup.

    Attributes:
        warmup_fraction: Fraction of total epochs used for linear warmup
            from ``min_scale`` to 1.0.
        min_scale: Minimum scale value (floor).
    """

    warmup_fraction: float = 0.1
    min_scale: float = 0.1

    def scale(self, epoch: int, total_epochs: int, **kwargs: float) -> float:
        if total_epochs <= 1:
            return 1.0

        warmup_steps = max(1, int(total_epochs * self.warmup_fraction))

        if epoch < warmup_steps:
            progress = epoch / warmup_steps
            return self.min_scale + (1.0 - self.min_scale) * progress

        progress = (epoch - warmup_steps) / max(1, total_epochs - warmup_steps)
        cosine = 0.5 * (1.0 + math.cos(math.pi * progress))
        return self.min_scale + (1.0 - self.min_scale) * cosine


@dataclass
class AdaptiveScheduler(Scheduler):
    """Adjusts scale based on recent improvement rate.

    When the improvement rate is high, the scale increases (more edits).
    When regression rate exceeds improvement rate, scale drops sharply.

    Attributes:
        base_scale: Default scale when no history is available.
        min_scale: Minimum scale.
        max_scale: Maximum scale (cap).
        boost_factor: Multiplier applied to scale when improvement is strong.
        penalty_factor: Multiplier applied when regression dominates.
    """

    base_scale: float = 0.5
    min_scale: float = 0.05
    max_scale: float = 1.0
    boost_factor: float = 1.5
    penalty_factor: float = 0.5

    def scale(
        self,
        epoch: int,
        total_epochs: int,
        improvement_rate: float = 0.0,
        regression_rate: float = 0.0,
        **kwargs: float,
    ) -> float:
        _ = epoch, total_epochs

        if improvement_rate + regression_rate == 0:
            return self.base_scale

        net = improvement_rate - regression_rate
        if net > 0.2:
            return min(self.max_scale, self.base_scale * self.boost_factor)
        elif net < -0.1:
            return max(self.min_scale, self.base_scale * self.penalty_factor)
        return self.base_scale


@dataclass
class CombinedScheduler(Scheduler):
    """Combines cosine decay with adaptive adjustment.

    The base scale comes from the cosine scheduler; it is then modulated
    by the adaptive scheduler's response to recent validation results.

    Attributes:
        cosine: The decay component.
        adaptive: The adaptive component.
        adaptive_weight: How much weight to give the adaptive signal
            (0 = pure cosine, 1 = pure adaptive).
    """

    cosine: Scheduler = field(default_factory=CosineDecayScheduler)
    adaptive: Scheduler = field(default_factory=AdaptiveScheduler)
    adaptive_weight: float = 0.3

    def scale(
        self,
        epoch: int,
        total_epochs: int,
        **kwargs: float,
    ) -> float:
        cosine_val = self.cosine.scale(epoch, total_epochs, **kwargs)
        adaptive_val = self.adaptive.scale(epoch, total_epochs, **kwargs)
        blended = (1.0 - self.adaptive_weight) * cosine_val + self.adaptive_weight * adaptive_val
        return max(0.0, min(1.0, blended))
