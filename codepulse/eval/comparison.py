"""Exact record alignment for paired evaluation comparisons."""

from __future__ import annotations

from collections.abc import Hashable
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

Left = TypeVar("Left")
Right = TypeVar("Right")
Key = TypeVar("Key", bound=Hashable)


def align_exact(
    left: Iterable[Left],
    right: Iterable[Right],
    *,
    left_key: Callable[[Left], Key],
    right_key: Callable[[Right], Key],
    left_name: str = "left",
    right_name: str = "right",
) -> list[tuple[Left, Right]]:
    """Align two collections by unique key and reject coverage drift."""
    left_index, order = _index_unique(left, left_key, left_name)
    right_index, _ = _index_unique(right, right_key, right_name)
    missing_right = set(left_index) - set(right_index)
    missing_left = set(right_index) - set(left_index)
    if missing_right or missing_left:
        details: list[str] = []
        if missing_right:
            details.append(f"missing from {right_name}: {_display_keys(missing_right)}")
        if missing_left:
            details.append(f"missing from {left_name}: {_display_keys(missing_left)}")
        raise ValueError("comparison coverage mismatch: " + "; ".join(details))
    return [(left_index[key], right_index[key]) for key in order]


def _index_unique(
    records: Iterable[Left],
    key_fn: Callable[[Left], Key],
    name: str,
) -> tuple[dict[Key, Left], list[Key]]:
    index: dict[Key, Left] = {}
    order: list[Key] = []
    for record in records:
        key = key_fn(record)
        if key in index:
            raise ValueError(f"duplicate {name} comparison key: {key!r}")
        index[key] = record
        order.append(key)
    return index, order


def _display_keys(keys: set[Key]) -> str:
    return ", ".join(sorted(repr(key) for key in keys))
