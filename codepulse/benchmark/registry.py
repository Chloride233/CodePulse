"""Benchmark registry — 内置行业基准的注册与管理。

Known benchmarks:
- SWE-bench Lite   (300 Python bug-fix tasks from real GitHub issues)
- SWE-bench Verified (~500 Python bug-fix tasks, hand-verified)
- HumanEval        (164 Python function-completion tasks)
- MBPP             (~974 Python introductory programming tasks)
- AACR-Bench       (code-review benchmark over multiple languages)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codepulse.data.models import TaskCategory, TaskSource

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BenchmarkDef:
    """Definition of a built-in benchmark dataset.

    Attributes:
        name: Short unique identifier (e.g. ``"swe-bench-lite"``).
        description: Human-readable description.
        source: Corresponding :class:`TaskSource` enum value.
        category: Predominant :class:`TaskCategory`.
        n_tasks: Approximate number of tasks (may vary with dataset version).
        languages: Programming languages covered.
        difficulty_distribution: Mapping difficulty → approximate count.
        download_url: Public URL to obtain the dataset (``None`` if not
            freely downloadable).
        expected_path: Relative path under ``datasets/`` where the data
            file should be placed (e.g. ``"swe-bench/lite.jsonl"``).
        loader_cls: Fully-qualified class name of the loader to use, or
            ``"custom"`` for the :class:`CustomDatasetLoader`.
        published_baselines: Published scores for reference comparison,
            mapping metric name → value.
    """

    name: str
    description: str
    source: TaskSource
    category: TaskCategory
    n_tasks: int
    languages: list[str] = field(default_factory=lambda: ["python"])
    difficulty_distribution: dict[str, int] = field(default_factory=dict)
    download_url: str | None = None
    expected_path: str = ""
    loader_cls: str = "custom"
    published_baselines: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_BUILTIN_BENCHMARKS: dict[str, BenchmarkDef] = {}


def builtin_benchmarks() -> dict[str, BenchmarkDef]:
    """Return a copy of the built-in benchmark registry.

    Returns:
        Mapping of benchmark name → :class:`BenchmarkDef`.
    """
    return dict(_BUILTIN_BENCHMARKS)


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------


def _register(defn: BenchmarkDef) -> None:
    """Register a benchmark definition (internal helper)."""
    _BUILTIN_BENCHMARKS[defn.name] = defn


_register(
    BenchmarkDef(
        name="swe-bench-lite",
        description=(
            "SWE-bench Lite: 300 Python bug-fix tasks derived from real GitHub "
            "issues. Each task provides a codebase snapshot and a failing test; "
            "the agent must produce a patch that makes the test pass."
        ),
        source=TaskSource.SWE_BENCH,
        category=TaskCategory.BUG_FIX,
        n_tasks=300,
        languages=["python"],
        difficulty_distribution={"easy": 100, "medium": 150, "hard": 50},
        download_url="https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite",
        expected_path="swe-bench/swe_bench_lite.jsonl",
        loader_cls="codepulse.data.swe_bench.SweBenchLoader",
        published_baselines={
            "pass@1": 0.0,
        },
        metadata={
            "paper": "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?",
            "year": 2024,
        },
    )
)

_register(
    BenchmarkDef(
        name="synthetic-swe-bench",
        description=(
            "Synthetic SWE-bench-style tasks: 10 auto-generated Python bug-fix "
            "tasks for quick pipeline testing. No network required."
        ),
        source=TaskSource.CUSTOM,
        category=TaskCategory.BUG_FIX,
        n_tasks=10,
        languages=["python"],
        difficulty_distribution={"easy": 5, "medium": 3, "hard": 2},
        download_url=None,
        expected_path="swe-bench/synthetic.jsonl",
        loader_cls="custom",
    )
)

_register(
    BenchmarkDef(
        name="swe-bench-verified",
        description=(
            "SWE-bench Verified: ~500 hand-verified Python bug-fix tasks. "
            "Each instance has been validated by human annotators to ensure "
            "the problem statement, test patch, and solution patch are correct."
        ),
        source=TaskSource.SWE_BENCH,
        category=TaskCategory.BUG_FIX,
        n_tasks=500,
        languages=["python"],
        difficulty_distribution={"easy": 200, "medium": 200, "hard": 100},
        download_url="https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified",
        expected_path="swe-bench/verified.jsonl",
        loader_cls="codepulse.data.swe_bench.SweBenchLoader",
        published_baselines={
            "pass@1": 0.0,
        },
        metadata={
            "paper": "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?",
            "year": 2024,
        },
    )
)

_register(
    BenchmarkDef(
        name="humaneval",
        description=(
            "HumanEval: 164 hand-written Python function-completion tasks. "
            "Each task provides a function signature and docstring; the agent "
            "must implement the function body. Tested via hidden unit tests."
        ),
        source=TaskSource.CUSTOM,
        category=TaskCategory.BUG_FIX,
        n_tasks=164,
        languages=["python"],
        difficulty_distribution={"easy": 60, "medium": 70, "hard": 34},
        download_url="https://github.com/openai/human-eval",
        expected_path="humaneval/humaneval_test.jsonl",
        loader_cls="custom",
        published_baselines={
            "pass@1": 0.0,
        },
        metadata={
            "paper": "Evaluating Large Language Models Trained on Code",
            "year": 2021,
        },
    )
)

_register(
    BenchmarkDef(
        name="mbpp",
        description=(
            "MBPP (Mostly Basic Programming Problems): ~974 Python introductory "
            "programming tasks. Each task provides a description and a function "
            "signature; the agent must implement the correct function body."
        ),
        source=TaskSource.CUSTOM,
        category=TaskCategory.FEATURE,
        n_tasks=974,
        languages=["python"],
        difficulty_distribution={"easy": 400, "medium": 400, "hard": 174},
        download_url="https://github.com/google-research/google-research/tree/master/mbpp",
        expected_path="mbpp/mbpp_test.jsonl",
        loader_cls="custom",
        published_baselines={
            "pass@1": 0.0,
        },
        metadata={
            "paper": "Program Synthesis with Large Language Models",
            "year": 2021,
        },
    )
)

_register(
    BenchmarkDef(
        name="aacr-bench",
        description=(
            "AACR-Bench: Automated Code Review benchmark. Multi-language PR "
            "review tasks where the agent must produce a review comment matching "
            "the ground-truth expected review."
        ),
        source=TaskSource.AACR_BENCH,
        category=TaskCategory.CODE_REVIEW,
        n_tasks=1000,
        languages=["python", "javascript", "typescript", "java", "go", "rust"],
        difficulty_distribution={"easy": 333, "medium": 334, "hard": 333},
        download_url=None,  # Not publicly available at a stable URL
        expected_path="aacr-bench/data.jsonl",
        loader_cls="codepulse.data.aacr_bench.AacrBenchLoader",
        published_baselines={
            "bleu": 0.0,
        },
        metadata={
            "paper": "AACR-Bench: Automated Code Review Benchmark",
        },
    )
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class BenchmarkRegistry:
    """Registry for querying and resolving benchmark definitions.

    Usage::

        registry = BenchmarkRegistry()
        all_benches = registry.list_benchmarks()
        swe_bench = registry.get("swe-bench-lite")
    """

    def list_benchmarks(self) -> list[BenchmarkDef]:
        """List all registered benchmarks.

        Returns:
            All :class:`BenchmarkDef` objects in registration order.
        """
        return list(builtin_benchmarks().values())

    def get(self, name: str) -> BenchmarkDef | None:
        """Look up a benchmark by name (case-insensitive).

        Args:
            name: Benchmark name (e.g. ``"swe-bench-lite"``, ``"humaneval"``).

        Returns:
            The matching :class:`BenchmarkDef`, or ``None``.
        """
        return builtin_benchmarks().get(name.lower())

    def find_by_source(self, source: TaskSource) -> list[BenchmarkDef]:
        """Find all benchmarks matching a task source.

        Args:
            source: The :class:`TaskSource` to filter by.

        Returns:
            List of matching :class:`BenchmarkDef` objects.
        """
        return [b for b in self.list_benchmarks() if b.source == source]

    def resolve_data_path(self, defn: BenchmarkDef, base_dir: str = "datasets") -> Path:
        """Resolve the expected data file path for a benchmark.

        Args:
            defn: The benchmark definition.
            base_dir: Root dataset directory.

        Returns:
            Absolute path to where the data file should live.
        """
        return Path(base_dir) / defn.expected_path

    def is_available(self, defn: BenchmarkDef, base_dir: str = "datasets") -> bool:
        """Check whether the benchmark's data file exists on disk.

        Args:
            defn: The benchmark definition.
            base_dir: Root dataset directory.

        Returns:
            ``True`` if the file is present.
        """
        return self.resolve_data_path(defn, base_dir).exists()
