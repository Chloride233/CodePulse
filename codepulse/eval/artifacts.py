"""Small helpers for immutable evaluation artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable


def canonical_sha256(value: object) -> str:
    """Hash a JSON value using stable key ordering and separators."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: str | Path) -> str:
    """Return the SHA-256 digest of a file's exact bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load non-empty JSONL object records."""
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL record {line_number} must be an object")
        records.append(value)
    return records


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    """Write JSONL object records with a trailing newline."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = "\n".join(
        json.dumps(row, ensure_ascii=False) for row in rows
    )
    target.write_text(serialized + "\n", encoding="utf-8")


def ensure_outputs_available(paths: Iterable[Path], *, force: bool) -> None:
    """Reject an operation that would overwrite an existing artifact."""
    if force:
        return
    existing = next((path for path in paths if path.exists()), None)
    if existing is not None:
        raise FileExistsError(f"refusing to overwrite existing artifact: {existing}")
