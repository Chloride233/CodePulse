"""Tests for exact paired evaluation alignment."""

from __future__ import annotations

import pytest

from codepulse.eval.comparison import align_exact


def test_eval_comparison_aligns_by_key_in_left_order() -> None:
    left = [{"id": "a", "value": 1}, {"id": "b", "value": 2}]
    right = [{"id": "b", "value": 20}, {"id": "a", "value": 10}]

    pairs = align_exact(
        left,
        right,
        left_key=lambda row: row["id"],
        right_key=lambda row: row["id"],
    )

    assert [(left_row["value"], right_row["value"]) for left_row, right_row in pairs] == [
        (1, 10),
        (2, 20),
    ]


def test_eval_comparison_rejects_duplicates_and_coverage_drift() -> None:
    with pytest.raises(ValueError, match="duplicate left"):
        align_exact(
            [{"id": "a"}, {"id": "a"}],
            [{"id": "a"}],
            left_key=lambda row: row["id"],
            right_key=lambda row: row["id"],
        )
    with pytest.raises(ValueError, match="coverage mismatch"):
        align_exact(
            [{"id": "a"}],
            [{"id": "b"}],
            left_key=lambda row: row["id"],
            right_key=lambda row: row["id"],
        )
