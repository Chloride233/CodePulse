"""Tests for codepulse.benchmark.registry — benchmark registry."""
from __future__ import annotations

from codepulse.benchmark import BenchmarkRegistry, builtin_benchmarks
from codepulse.data.models import TaskCategory, TaskSource


class TestBenchmarkRegistry:
    """Tests for BenchmarkRegistry."""

    def setup_method(self) -> None:
        self.registry = BenchmarkRegistry()

    def test_list_benchmarks_returns_list(self) -> None:
        benches = self.registry.list_benchmarks()
        assert isinstance(benches, list)
        assert len(benches) >= 5  # swe-bench-lite, swe-bench-verified, humaneval, mbpp, aacr-bench

    def test_get_known_benchmark(self) -> None:
        defn = self.registry.get("swe-bench-lite")
        assert defn is not None
        assert defn.name == "swe-bench-lite"
        assert defn.n_tasks == 300
        assert defn.source == TaskSource.SWE_BENCH
        assert defn.category == TaskCategory.BUG_FIX
        assert defn.loader_cls == "codepulse.data.swe_bench.SweBenchLoader"

    def test_get_case_insensitive(self) -> None:
        defn = self.registry.get("HUMANEVAL")
        assert defn is not None
        assert defn.name == "humaneval"

    def test_get_unknown_returns_none(self) -> None:
        defn = self.registry.get("nonexistent-benchmark")
        assert defn is None

    def test_find_by_source(self) -> None:
        benches = self.registry.find_by_source(TaskSource.SWE_BENCH)
        assert len(benches) >= 2
        for b in benches:
            assert b.source == TaskSource.SWE_BENCH

    def test_find_by_custom_source(self) -> None:
        benches = self.registry.find_by_source(TaskSource.CUSTOM)
        assert len(benches) >= 2
        names = [b.name for b in benches]
        assert "humaneval" in names
        assert "mbpp" in names

    def test_resolve_data_path(self) -> None:
        defn = self.registry.get("swe-bench-lite")
        assert defn is not None
        path = self.registry.resolve_data_path(defn, base_dir="datasets")
        assert str(path) == "datasets\\swe-bench\\swe_bench_lite.jsonl" or str(path) == "datasets/swe-bench/swe_bench_lite.jsonl"
        assert path.suffix == ".jsonl"

    def test_is_available_returns_false_for_missing(self) -> None:
        defn = self.registry.get("swe-bench-verified")
        assert defn is not None
        available = self.registry.is_available(defn, base_dir="datasets")
        assert available is False

    def test_builtin_benchmarks_are_frozen(self) -> None:
        """builtin_benchmarks() returns a copy, not the mutable original."""
        benches = builtin_benchmarks()
        orig_count = len(benches)
        # Adding to the copy should not affect the original
        benches["fake"] = benches["swe-bench-lite"]  # type: ignore[assignment]
        assert len(builtin_benchmarks()) == orig_count

    def test_all_benchmarks_have_required_fields(self) -> None:
        for defn in self.registry.list_benchmarks():
            assert defn.name, "Benchmark missing name"
            assert defn.description, f"{defn.name} missing description"
            assert defn.expected_path, f"{defn.name} missing expected_path"
            assert defn.n_tasks > 0, f"{defn.name} has n_tasks=0"
            assert defn.languages, f"{defn.name} missing languages"

    def test_swe_bench_verified_has_correct_loader(self) -> None:
        defn = self.registry.get("swe-bench-verified")
        assert defn is not None
        assert defn.loader_cls == "codepulse.data.swe_bench.SweBenchLoader"

    def test_mbpp_is_custom_category(self) -> None:
        defn = self.registry.get("mbpp")
        assert defn is not None
        assert defn.category == TaskCategory.FEATURE
        assert defn.source == TaskSource.CUSTOM
