"""Rejected-edit buffer for the SkillOpt self-evolution cycle.

Stores rejected and accepted edits from the validation gate so the backward
pass can learn from failures.  The buffer groups rejections by edit type to
surface recurring anti-patterns.
"""

from __future__ import annotations

import time
from collections import defaultdict

from codepulse.evolve.prompt_edit import PromptEdit, RejectedEdit


class EditBuffer:
    """In-memory ring of rejected and accepted prompt edits.

    The buffer accumulates :class:`RejectedEdit` records and accepted
    (edit, score_delta) pairs during the Validate phase of each SkillOpt
    iteration.  Downstream consumers — primarily the backward pass — query
    :meth:`get_negative_signals` or :meth:`get_patterns` to avoid repeating
    the same mistakes.
    """

    def __init__(self) -> None:
        self._rejected: list[RejectedEdit] = []
        self._accepted: list[tuple[PromptEdit, float]] = []

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def add_rejected(
        self, edit: PromptEdit, score_delta: float, reason: str
    ) -> None:
        """Record an edit that was validated and found to cause regression.

        Args:
            edit: The prompt edit that was rejected.
            score_delta: Change in aggregate score (expected negative).
            reason: Human-readable explanation of why the edit was rejected.
        """
        record = RejectedEdit(
            edit=edit,
            score_delta=score_delta,
            rejection_reason=reason,
            timestamp=time.time(),
        )
        self._rejected.append(record)

    def add_accepted(self, edit: PromptEdit, score_delta: float) -> None:
        """Record an edit that passed validation and improved scores.

        Args:
            edit: The prompt edit that was accepted.
            score_delta: Change in aggregate score (expected positive).
        """
        self._accepted.append((edit, score_delta))

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get_negative_signals(self) -> list[RejectedEdit]:
        """Return all rejected edits as negative training signals.

        Returns:
            Chronologically ordered list of rejected edits.
        """
        return list(self._rejected)

    def get_patterns(self) -> dict[str, list[RejectedEdit]]:
        """Group rejected edits by their ``edit_type``.

        Useful for the backward pass to identify which *kind* of edit is
        most often rejected and should be avoided or approached differently.

        Returns:
            Mapping from :attr:`EditType` value to the list of rejected
            edits of that type.
        """
        patterns: dict[str, list[RejectedEdit]] = defaultdict(list)
        for record in self._rejected:
            patterns[record.edit.edit_type].append(record)
        return dict(patterns)

    def get_stats(self) -> dict[str, object]:
        """Return summary statistics for the current buffer contents.

        Returns:
            Dictionary with keys:

            - ``rejected_count``: number of rejected edits
            - ``accepted_count``: number of accepted edits
            - ``avg_rejected_delta``: mean score_delta of rejected edits
              (``0.0`` when empty)
            - ``avg_accepted_delta``: mean score_delta of accepted edits
              ``0.0`` when empty
        """
        rej_deltas = [r.score_delta for r in self._rejected]
        acc_deltas = [delta for _, delta in self._accepted]

        avg_rej = sum(rej_deltas) / len(rej_deltas) if rej_deltas else 0.0
        avg_acc = sum(acc_deltas) / len(acc_deltas) if acc_deltas else 0.0

        return {
            "rejected_count": len(self._rejected),
            "accepted_count": len(self._accepted),
            "avg_rejected_delta": avg_rej,
            "avg_accepted_delta": avg_acc,
        }
