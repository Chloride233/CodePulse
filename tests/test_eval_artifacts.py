"""Tests for shared immutable experiment artifact helpers."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from codepulse.eval.artifacts import (
    canonical_sha256,
    ensure_outputs_available,
    file_sha256,
    load_jsonl,
    write_jsonl,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_eval_artifacts_jsonl_round_trip_preserves_rows(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    rows = [{"id": "one", "text": "calibration"}, {"id": "two", "value": 2}]

    write_jsonl(path, rows)

    assert load_jsonl(path) == rows
    assert path.read_bytes().endswith(b"\n")
    assert file_sha256(path) == hashlib.sha256(path.read_bytes()).hexdigest()
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})


def test_eval_artifacts_existing_output_requires_explicit_force(tmp_path: Path) -> None:
    path = tmp_path / "existing.jsonl"
    path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        ensure_outputs_available([path], force=False)

    ensure_outputs_available([path], force=True)
