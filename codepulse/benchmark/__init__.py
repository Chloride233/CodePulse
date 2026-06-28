"""Benchmark registry and runner — 行业基准评测。

Provides:
- A registry of known industry benchmarks (SWE-Bench, HumanEval, MBPP, etc.)
- Auto-download and cache management
- Benchmark-aware evaluation (run → score → compare against published baselines)
"""

from codepulse.benchmark.registry import BenchmarkDef, BenchmarkRegistry, builtin_benchmarks

__all__ = [
    "BenchmarkDef",
    "BenchmarkRegistry",
    "builtin_benchmarks",
]
