"""Three-level experience evolution: Lesson → Pattern → Instinct.

Captures observations from evaluation failures and self-evolution rounds,
generalises them into cross-task patterns, and promotes high-confidence
patterns into automatic instincts that shape future agent behaviour.

Inspired by how humans learn: a single mistake → a lesson → repeated
observations → a pattern → automatic behaviour → an instinct.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Lesson:
    """A single observation or lesson from an evaluation or evolution round.

    Attributes:
        lesson_id: Unique identifier.
        observation: Human-readable description of what was observed.
        context: Surrounding context (task_id, epoch, scores, etc.).
        timestamp: ISO-format timestamp of when the lesson was recorded.
        source: Where this lesson came from (e.g. 'evaluation', 'evolution').
    """

    lesson_id: str
    observation: str
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    source: str = ""


@dataclass(frozen=True)
class Pattern:
    """A cross-task generalisation derived from repeated lessons.

    Attributes:
        pattern_id: Unique identifier.
        observation: Generalised observation text.
        confidence: Confidence score in [0, 1] based on supporting evidence.
        lesson_count: Number of lessons that contributed to this pattern.
        verification_count: Number of times this pattern has been verified.
        tags: Categorisation tags (e.g. 'blackhole', 'prompt', 'tool').
        created_at: ISO-format creation timestamp.
    """

    pattern_id: str
    observation: str
    confidence: float = 0.0
    lesson_count: int = 0
    verification_count: int = 0
    tags: list[str] = field(default_factory=list)
    created_at: str = ""


@dataclass(frozen=True)
class Instinct:
    """An automatic behavioural rule promoted from a verified pattern.

    Instincts are intended to be automatically injected into agent prompts
    or system configuration without manual intervention.

    Attributes:
        instinct_id: Unique identifier.
        pattern_id: The pattern this instinct was promoted from.
        rule: The behavioural rule or prompt instruction.
        confidence: Confidence score in [0, 1] (≥0.8 for promotion).
        verification_count: Number of verifications (≥3 for promotion).
        active: Whether this instinct is currently active.
        promoted_at: ISO-format promotion timestamp.
    """

    instinct_id: str
    pattern_id: str
    rule: str
    confidence: float = 0.0
    verification_count: int = 0
    active: bool = True
    promoted_at: str = ""


_PATTERN_PROMOTION_THRESHOLD = 2
_INSTINCT_CONFIDENCE_THRESHOLD = 0.8
_INSTINCT_VERIFICATION_THRESHOLD = 3


class ExperienceEvolution:
    """Three-level experience evolution engine.

    Lessons are recorded individually. When the same observation appears
    multiple times, it is promoted to a Pattern. When a Pattern reaches
    high confidence and sufficient verification, it is promoted to an
    Instinct that can be applied automatically.

    Attributes:
        lessons: All recorded lessons.
        patterns: All extracted patterns.
        instincts: All promoted instincts.
    """

    def __init__(self) -> None:
        self.lessons: list[Lesson] = []
        self.patterns: list[Pattern] = []
        self.instincts: list[Instinct] = []
        self._next_id: int = 0

    def _new_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id:04d}"

    def record_lesson(
        self,
        observation: str,
        context: dict[str, Any] | None = None,
        source: str = "",
    ) -> Lesson:
        """Record a single lesson.

        Args:
            observation: What was observed.
            context: Surrounding context (task_id, scores, etc.).
            source: Source identifier (e.g. 'evaluation', 'evolution').

        Returns:
            The created Lesson.
        """
        lesson = Lesson(
            lesson_id=self._new_id("lesson"),
            observation=observation,
            context=context or {},
            timestamp=datetime.now(UTC).isoformat(),
            source=source,
        )
        self.lessons.append(lesson)
        logger.debug("Lesson recorded: %s", observation)
        return lesson

    def try_promote_to_pattern(
        self,
        min_occurrences: int = _PATTERN_PROMOTION_THRESHOLD,
    ) -> list[Pattern]:
        """Group repeated lessons into Patterns.

        Lessons with the same observation text are counted. If a text
        appears at least ``min_occurrences`` times, it is promoted to a
        Pattern. Existing patterns are skipped.

        Args:
            min_occurrences: Minimum number of identical observations
                required for promotion to Pattern.

        Returns:
            List of newly created Patterns.
        """
        existing_observations = {p.observation for p in self.patterns}
        counts: dict[str, list[Lesson]] = defaultdict(list)

        for lesson in self.lessons:
            counts[lesson.observation].append(lesson)

        new_patterns: list[Pattern] = []
        for observation, group in counts.items():
            if observation in existing_observations:
                continue
            if len(group) >= min_occurrences:
                tags = self._infer_tags(observation)
                pattern = Pattern(
                    pattern_id=self._new_id("pattern"),
                    observation=observation,
                    confidence=round(min(1.0, len(group) / 10.0), 4),
                    lesson_count=len(group),
                    tags=tags,
                    created_at=datetime.now(UTC).isoformat(),
                )
                self.patterns.append(pattern)
                existing_observations.add(observation)
                new_patterns.append(pattern)
                logger.info(
                    "Pattern promoted: '%s' (%d lessons, tags=%s)",
                    observation,
                    len(group),
                    tags,
                )

        return new_patterns

    def try_promote_to_instinct(
        self,
        confidence_threshold: float = _INSTINCT_CONFIDENCE_THRESHOLD,
        verification_threshold: int = _INSTINCT_VERIFICATION_THRESHOLD,
    ) -> list[Instinct]:
        """Promote high-confidence Patterns to Instincts.

        Args:
            confidence_threshold: Minimum confidence for promotion.
            verification_threshold: Minimum verification count.

        Returns:
            List of newly promoted Instincts.
        """
        existing_pattern_ids = {i.pattern_id for i in self.instincts}
        new_instincts: list[Instinct] = []

        for pattern in self.patterns:
            if pattern.pattern_id in existing_pattern_ids:
                continue
            if (
                pattern.confidence >= confidence_threshold
                and pattern.verification_count >= verification_threshold
            ):
                rule = self._pattern_to_rule(pattern)
                instinct = Instinct(
                    instinct_id=self._new_id("instinct"),
                    pattern_id=pattern.pattern_id,
                    rule=rule,
                    confidence=pattern.confidence,
                    verification_count=pattern.verification_count,
                    active=True,
                    promoted_at=datetime.now(UTC).isoformat(),
                )
                self.instincts.append(instinct)
                existing_pattern_ids.add(pattern.pattern_id)
                new_instincts.append(instinct)
                logger.info(
                    "Instinct promoted: '%s' (confidence=%.2f, verifications=%d)",
                    instinct.rule[:60],
                    instinct.confidence,
                    instinct.verification_count,
                )

        return new_instincts

    def verify_pattern(self, pattern_id: str) -> bool:
        """Increment verification count for a pattern.

        Args:
            pattern_id: The pattern to verify.

        Returns:
            True if the pattern was found and updated.
        """
        for i, pattern in enumerate(self.patterns):
            if pattern.pattern_id == pattern_id:
                self.patterns[i] = Pattern(
                    pattern_id=pattern.pattern_id,
                    observation=pattern.observation,
                    confidence=min(1.0, pattern.confidence + 0.05),
                    lesson_count=pattern.lesson_count,
                    verification_count=pattern.verification_count + 1,
                    tags=pattern.tags,
                    created_at=pattern.created_at,
                )
                return True
        return False

    def get_active_instincts(self) -> list[Instinct]:
        """Return all currently active instincts.

        Returns:
            List of active Instincts.
        """
        return [i for i in self.instincts if i.active]

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics.

        Returns:
            Dictionary with counts and ratios.
        """
        total_lessons = len(self.lessons)
        return {
            "lessons": total_lessons,
            "patterns": len(self.patterns),
            "instincts": len(self.instincts),
            "active_instincts": len(self.get_active_instincts()),
            "pattern_ratio": round(
                len(self.patterns) / max(total_lessons, 1), 4
            ),
        }

    @staticmethod
    def _infer_tags(observation: str) -> list[str]:
        """Infer categorisation tags from observation text."""
        tags: list[str] = []
        text = observation.lower()
        if "loop" in text or "retry" in text or "repeat" in text:
            tags.append("blackhole")
        if "token" in text or "cost" in text:
            tags.append("efficiency")
        if "prompt" in text or "instruction" in text:
            tags.append("prompt")
        if "tool" in text or "function" in text or "call" in text:
            tags.append("tool")
        if "context" in text or "memory" in text:
            tags.append("context")
        if not tags:
            tags.append("general")
        return tags

    @staticmethod
    def _pattern_to_rule(pattern: Pattern) -> str:
        """Convert a pattern observation into an actionable rule."""
        return (
            f"Rule (from pattern '{pattern.pattern_id}'): "
            f"{pattern.observation}"
        )
