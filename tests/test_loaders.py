"""Tests for data loaders — SweBenchLoader, AacrBenchLoader, CustomDatasetLoader.

Validates instantiation, DatasetLoader protocol compliance, JSONL parsing,
validation logic, and error handling for missing files and invalid records.
"""

from __future__ import annotations

import json

import pytest

from codepulse.data.aacr_bench import AacrBenchLoader
from codepulse.data.custom_loader import CustomDatasetLoader
from codepulse.data.models import Difficulty, Task, TaskCategory, TaskSource
from codepulse.data.protocols import DatasetLoader
from codepulse.data.swe_bench import SweBenchLoader

# ---------------------------------------------------------------------------
# Fixtures — temp JSONL files
# ---------------------------------------------------------------------------


@pytest.fixture()
def swe_bench_file(tmp_path):
    """Create a temp SWE-bench JSONL file with one valid record."""
    record = {
        "instance_id": "test-001",
        "repo": "test/repo",
        "base_commit": "abc123",
        "problem_statement": "Fix bug",
        "patch": "diff --git a/foo.py",
        "test_patch": "def test_foo():",
    }
    path = tmp_path / "swe_bench.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return str(path)


@pytest.fixture()
def swe_bench_file_multi(tmp_path):
    """Create a temp SWE-bench JSONL file with two valid records."""
    records = [
        {
            "instance_id": "test-001",
            "repo": "test/repo",
            "base_commit": "abc123",
            "problem_statement": "Fix bug",
            "patch": "diff --git a/foo.py",
            "test_patch": "def test_foo():",
        },
        {
            "instance_id": "test-002",
            "repo": "other/repo",
            "base_commit": "def456",
            "problem_statement": "Add feature",
            "patch": "diff --git a/bar.py",
        },
    ]
    path = tmp_path / "swe_multi.jsonl"
    lines = [json.dumps(r) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


@pytest.fixture()
def aacr_bench_file(tmp_path):
    """Create a temp AACR-Bench JSONL file with one valid record."""
    record = {
        "pr_id": "pr-001",
        "pr_title": "Fix memory leak",
        "expected_review": "The buffer is not released in the finally block.",
        "pr_body": "See title.",
        "repo": "org/repo",
        "language": "python",
        "review_comments": [
            {"file": "src/main.py", "line": 42, "body": "Missing null check."}
        ],
    }
    path = tmp_path / "aacr_bench.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return str(path)


@pytest.fixture()
def custom_file(tmp_path):
    """Create a temp custom-format JSONL file with one valid record."""
    record = {
        "task_id": "custom-001",
        "category": "bug_fix",
        "difficulty": "easy",
        "language": "python",
        "description": "Fix add()",
        "expected_output": "def add(a,b): return a+b",
    }
    path = tmp_path / "custom.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return str(path)


@pytest.fixture()
def custom_file_multi(tmp_path):
    """Create a temp custom JSONL file with two valid records."""
    records = [
        {
            "task_id": "custom-001",
            "category": "bug_fix",
            "difficulty": "easy",
            "language": "python",
            "description": "Fix add()",
            "expected_output": "def add(a,b): return a+b",
        },
        {
            "task_id": "custom-002",
            "category": "feature",
            "difficulty": "medium",
            "language": "rust",
            "description": "Implement binary search",
            "expected_output": "fn binary_search(arr: &[i32], target: i32) -> Option<usize>",
            "input_code": "fn binary_search(arr: &[i32], target: i32) -> Option<usize> { todo!() }",
            "test_cases": ["test_empty_array", "test_found", "test_not_found"],
            "metadata": {"source": "manual", "priority": 1},
        },
    ]
    path = tmp_path / "custom_multi.jsonl"
    lines = [json.dumps(r) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# 1. Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    """All three loaders satisfy the DatasetLoader runtime_checkable protocol."""

    def test_swe_bench_loader_satisfies_protocol(self):
        assert isinstance(SweBenchLoader(), DatasetLoader)

    def test_aacr_bench_loader_satisfies_protocol(self):
        assert isinstance(AacrBenchLoader(), DatasetLoader)

    def test_custom_loader_satisfies_protocol(self):
        assert isinstance(CustomDatasetLoader(), DatasetLoader)

    def test_swe_bench_loader_has_load_method(self):
        loader = SweBenchLoader()
        assert hasattr(loader, "load") and callable(loader.load)

    def test_swe_bench_loader_has_validate_method(self):
        loader = SweBenchLoader()
        assert hasattr(loader, "validate") and callable(loader.validate)

    def test_aacr_bench_loader_has_load_method(self):
        loader = AacrBenchLoader()
        assert hasattr(loader, "load") and callable(loader.load)

    def test_aacr_bench_loader_has_validate_method(self):
        loader = AacrBenchLoader()
        assert hasattr(loader, "validate") and callable(loader.validate)

    def test_custom_loader_has_load_method(self):
        loader = CustomDatasetLoader()
        assert hasattr(loader, "load") and callable(loader.load)

    def test_custom_loader_has_validate_method(self):
        loader = CustomDatasetLoader()
        assert hasattr(loader, "validate") and callable(loader.validate)


# ---------------------------------------------------------------------------
# 2. SweBenchLoader
# ---------------------------------------------------------------------------


class TestSweBenchLoader:
    """SweBenchLoader load, validate, and field mapping."""

    def test_instantiation(self):
        loader = SweBenchLoader()
        assert loader is not None

    def test_load_returns_list_of_tasks(self, swe_bench_file):
        loader = SweBenchLoader()
        tasks = loader.load(swe_bench_file)
        assert isinstance(tasks, list)
        assert len(tasks) == 1
        assert isinstance(tasks[0], Task)

    def test_load_fields_match_expected(self, swe_bench_file):
        loader = SweBenchLoader()
        task = loader.load(swe_bench_file)[0]

        assert task.task_id == "test-001"
        assert task.source == TaskSource.SWE_BENCH
        assert task.category == TaskCategory.BUG_FIX
        assert task.difficulty == Difficulty.MEDIUM
        assert task.language == "python"
        assert task.input["description"] == "Fix bug"
        assert task.input["hints"] == ""
        assert task.ground_truth["patch"] == "diff --git a/foo.py"
        assert task.ground_truth["test_patch"] == "def test_foo():"
        assert task.metadata["repo"] == "test/repo"
        assert task.metadata["base_commit"] == "abc123"

    def test_load_multiple_records(self, swe_bench_file_multi):
        loader = SweBenchLoader()
        tasks = loader.load(swe_bench_file_multi)
        assert len(tasks) == 2
        assert tasks[0].task_id == "test-001"
        assert tasks[1].task_id == "test-002"

    def test_load_without_optional_fields(self, tmp_path):
        """Records missing optional fields (hints_text, repo, etc.) still load."""
        record = {
            "instance_id": "minimal-001",
            "problem_statement": "Minimal task",
            "patch": "diff --git a/x.py",
        }
        path = tmp_path / "minimal.jsonl"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        loader = SweBenchLoader()
        tasks = loader.load(str(path))
        assert len(tasks) == 1
        task = tasks[0]
        assert task.task_id == "minimal-001"
        assert task.metadata["repo"] == ""
        assert task.metadata["base_commit"] == ""

    def test_load_skips_missing_required_fields(self, tmp_path, caplog):
        """Records missing instance_id, problem_statement, or patch are skipped."""
        bad_record = {"repo": "x/y", "base_commit": "aaa"}
        path = tmp_path / "bad.jsonl"
        path.write_text(json.dumps(bad_record) + "\n", encoding="utf-8")

        loader = SweBenchLoader()
        tasks = loader.load(str(path))
        assert tasks == []

    def test_load_skips_invalid_json(self, tmp_path):
        path = tmp_path / "corrupt.jsonl"
        path.write_text("not valid json\n", encoding="utf-8")

        loader = SweBenchLoader()
        tasks = loader.load(str(path))
        assert tasks == []

    def test_load_skips_empty_lines(self, tmp_path):
        record = {
            "instance_id": "ok-001",
            "problem_statement": "Something",
            "patch": "diff",
        }
        path = tmp_path / "sparse.jsonl"
        path.write_text("\n" + json.dumps(record) + "\n\n", encoding="utf-8")

        loader = SweBenchLoader()
        tasks = loader.load(str(path))
        assert len(tasks) == 1

    def test_validate_valid_task(self, swe_bench_file):
        loader = SweBenchLoader()
        task = loader.load(swe_bench_file)[0]
        assert loader.validate(task) is True

    def test_validate_empty_task_id(self):
        task = Task(
            task_id="",
            source=TaskSource.SWE_BENCH,
            category=TaskCategory.BUG_FIX,
            difficulty=Difficulty.MEDIUM,
            language="python",
            input={"description": "Fix bug"},
            ground_truth={"patch": "diff"},
        )
        assert SweBenchLoader().validate(task) is False

    def test_validate_missing_description(self):
        task = Task(
            task_id="t-001",
            source=TaskSource.SWE_BENCH,
            category=TaskCategory.BUG_FIX,
            difficulty=Difficulty.MEDIUM,
            language="python",
            input={},
            ground_truth={"patch": "diff"},
        )
        assert SweBenchLoader().validate(task) is False

    def test_validate_missing_patch(self):
        task = Task(
            task_id="t-001",
            source=TaskSource.SWE_BENCH,
            category=TaskCategory.BUG_FIX,
            difficulty=Difficulty.MEDIUM,
            language="python",
            input={"description": "Fix bug"},
            ground_truth={},
        )
        assert SweBenchLoader().validate(task) is False


# ---------------------------------------------------------------------------
# 3. AacrBenchLoader
# ---------------------------------------------------------------------------


class TestAacrBenchLoader:
    """AacrBenchLoader load, validate, and field mapping."""

    def test_instantiation(self):
        loader = AacrBenchLoader()
        assert loader is not None

    def test_load_returns_list_of_tasks(self, aacr_bench_file):
        loader = AacrBenchLoader()
        tasks = loader.load(aacr_bench_file)
        assert isinstance(tasks, list)
        assert len(tasks) == 1
        assert isinstance(tasks[0], Task)

    def test_load_fields_match_expected(self, aacr_bench_file):
        loader = AacrBenchLoader()
        task = loader.load(aacr_bench_file)[0]

        assert task.task_id == "pr-001"
        assert task.source == TaskSource.AACR_BENCH
        assert task.category == TaskCategory.CODE_REVIEW
        assert task.difficulty == Difficulty.MEDIUM
        assert task.language == "python"
        assert task.input["title"] == "Fix memory leak"
        assert task.input["body"] == "See title."
        assert len(task.input["comments"]) == 1
        assert task.ground_truth["expected_review"] == (
            "The buffer is not released in the finally block."
        )
        assert task.metadata["repo"] == "org/repo"

    def test_load_detects_language_from_comments(self, tmp_path):
        """When language field is absent, infer from review_comments file extensions."""
        record = {
            "pr_id": "pr-lang",
            "pr_title": "Update JS module",
            "expected_review": "Looks good.",
            "review_comments": [
                {"file": "src/index.js", "line": 10, "body": "ok"},
                {"file": "src/utils.js", "line": 5, "body": "ok"},
                {"file": "src/helper.ts", "line": 1, "body": "ok"},
            ],
        }
        path = tmp_path / "lang_detect.jsonl"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        loader = AacrBenchLoader()
        task = loader.load(str(path))[0]
        assert task.language == "javascript"

    def test_load_language_unknown_when_no_extensions(self, tmp_path):
        record = {
            "pr_id": "pr-unknown",
            "pr_title": "Docs update",
            "expected_review": "Approved.",
        }
        path = tmp_path / "no_ext.jsonl"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        loader = AacrBenchLoader()
        task = loader.load(str(path))[0]
        assert task.language == "unknown"

    def test_load_skips_missing_required_fields(self, tmp_path):
        bad_record = {"repo": "x/y"}
        path = tmp_path / "bad_aacr.jsonl"
        path.write_text(json.dumps(bad_record) + "\n", encoding="utf-8")

        loader = AacrBenchLoader()
        tasks = loader.load(str(path))
        assert tasks == []

    def test_load_skips_invalid_json(self, tmp_path):
        path = tmp_path / "corrupt_aacr.jsonl"
        path.write_text("{bad json\n", encoding="utf-8")

        loader = AacrBenchLoader()
        tasks = loader.load(str(path))
        assert tasks == []

    def test_validate_valid_task(self, aacr_bench_file):
        loader = AacrBenchLoader()
        task = loader.load(aacr_bench_file)[0]
        assert loader.validate(task) is True

    def test_validate_empty_task_id(self):
        task = Task(
            task_id="",
            source=TaskSource.AACR_BENCH,
            category=TaskCategory.CODE_REVIEW,
            difficulty=Difficulty.MEDIUM,
            language="python",
            input={"title": "PR title"},
            ground_truth={"expected_review": "Looks good."},
        )
        assert AacrBenchLoader().validate(task) is False

    def test_validate_missing_title(self):
        task = Task(
            task_id="pr-001",
            source=TaskSource.AACR_BENCH,
            category=TaskCategory.CODE_REVIEW,
            difficulty=Difficulty.MEDIUM,
            language="python",
            input={},
            ground_truth={"expected_review": "Looks good."},
        )
        assert AacrBenchLoader().validate(task) is False

    def test_validate_missing_expected_review(self):
        task = Task(
            task_id="pr-001",
            source=TaskSource.AACR_BENCH,
            category=TaskCategory.CODE_REVIEW,
            difficulty=Difficulty.MEDIUM,
            language="python",
            input={"title": "PR title"},
            ground_truth={},
        )
        assert AacrBenchLoader().validate(task) is False


# ---------------------------------------------------------------------------
# 4. CustomDatasetLoader
# ---------------------------------------------------------------------------


class TestCustomDatasetLoader:
    """CustomDatasetLoader load, validate, and field mapping."""

    def test_instantiation(self):
        loader = CustomDatasetLoader()
        assert loader is not None

    def test_load_returns_list_of_tasks(self, custom_file):
        loader = CustomDatasetLoader()
        tasks = loader.load(custom_file)
        assert isinstance(tasks, list)
        assert len(tasks) == 1
        assert isinstance(tasks[0], Task)

    def test_load_fields_match_expected(self, custom_file):
        loader = CustomDatasetLoader()
        task = loader.load(custom_file)[0]

        assert task.task_id == "custom-001"
        assert task.source == TaskSource.CUSTOM
        assert task.category == TaskCategory.BUG_FIX
        assert task.difficulty == Difficulty.EASY
        assert task.language == "python"
        assert task.input["description"] == "Fix add()"
        assert task.input["input_code"] == ""
        assert task.ground_truth["expected_output"] == "def add(a,b): return a+b"
        assert task.ground_truth["test_cases"] == []
        assert task.metadata == {}

    def test_load_with_all_optional_fields(self, custom_file_multi):
        loader = CustomDatasetLoader()
        tasks = loader.load(custom_file_multi)
        assert len(tasks) == 2

        task2 = tasks[1]
        assert task2.task_id == "custom-002"
        assert task2.category == TaskCategory.FEATURE
        assert task2.difficulty == Difficulty.MEDIUM
        assert task2.language == "rust"
        assert task2.input["description"] == "Implement binary search"
        assert "todo!()" in task2.input["input_code"]
        assert len(task2.ground_truth["test_cases"]) == 3
        assert task2.metadata["source"] == "manual"
        assert task2.metadata["priority"] == 1

    def test_load_unknown_category_defaults_to_feature(self, tmp_path):
        record = {
            "task_id": "cat-test",
            "category": "unknown_category",
            "difficulty": "easy",
            "language": "python",
            "description": "Some task",
            "expected_output": "result",
        }
        path = tmp_path / "unknown_cat.jsonl"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        loader = CustomDatasetLoader()
        task = loader.load(str(path))[0]
        assert task.category == TaskCategory.FEATURE

    def test_load_unknown_difficulty_defaults_to_medium(self, tmp_path):
        record = {
            "task_id": "diff-test",
            "category": "bug_fix",
            "difficulty": "extreme",
            "language": "python",
            "description": "Some task",
            "expected_output": "result",
        }
        path = tmp_path / "unknown_diff.jsonl"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        loader = CustomDatasetLoader()
        task = loader.load(str(path))[0]
        assert task.difficulty == Difficulty.MEDIUM

    def test_load_missing_language_defaults_to_unknown(self, tmp_path):
        record = {
            "task_id": "no-lang",
            "description": "Task without language",
            "expected_output": "output",
        }
        path = tmp_path / "no_lang.jsonl"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        loader = CustomDatasetLoader()
        task = loader.load(str(path))[0]
        assert task.language == "unknown"

    def test_load_skips_missing_required_fields(self, tmp_path):
        bad_record = {"language": "python", "category": "bug_fix"}
        path = tmp_path / "bad_custom.jsonl"
        path.write_text(json.dumps(bad_record) + "\n", encoding="utf-8")

        loader = CustomDatasetLoader()
        tasks = loader.load(str(path))
        assert tasks == []

    def test_load_skips_invalid_json(self, tmp_path):
        path = tmp_path / "corrupt_custom.jsonl"
        path.write_text("{{{invalid}}}\n", encoding="utf-8")

        loader = CustomDatasetLoader()
        tasks = loader.load(str(path))
        assert tasks == []

    def test_validate_valid_task(self, custom_file):
        loader = CustomDatasetLoader()
        task = loader.load(custom_file)[0]
        assert loader.validate(task) is True

    def test_validate_empty_task_id(self):
        task = Task(
            task_id="",
            source=TaskSource.CUSTOM,
            category=TaskCategory.BUG_FIX,
            difficulty=Difficulty.EASY,
            language="python",
            input={"description": "Fix add()"},
            ground_truth={"expected_output": "result"},
        )
        assert CustomDatasetLoader().validate(task) is False

    def test_validate_missing_description(self):
        task = Task(
            task_id="custom-001",
            source=TaskSource.CUSTOM,
            category=TaskCategory.BUG_FIX,
            difficulty=Difficulty.EASY,
            language="python",
            input={},
            ground_truth={"expected_output": "result"},
        )
        assert CustomDatasetLoader().validate(task) is False

    def test_validate_missing_expected_output(self):
        task = Task(
            task_id="custom-001",
            source=TaskSource.CUSTOM,
            category=TaskCategory.BUG_FIX,
            difficulty=Difficulty.EASY,
            language="python",
            input={"description": "Fix add()"},
            ground_truth={},
        )
        assert CustomDatasetLoader().validate(task) is False


# ---------------------------------------------------------------------------
# 5. FileNotFoundError on missing paths
# ---------------------------------------------------------------------------


class TestFileNotFound:
    """All loaders raise FileNotFoundError for non-existent paths."""

    def test_swe_bench_missing_file_raises(self):
        loader = SweBenchLoader()
        with pytest.raises(FileNotFoundError, match="Dataset file not found"):
            loader.load("/nonexistent/path/swe.jsonl")

    def test_aacr_bench_missing_file_raises(self):
        loader = AacrBenchLoader()
        with pytest.raises(FileNotFoundError, match="Dataset file not found"):
            loader.load("/nonexistent/path/aacr.jsonl")

    def test_custom_missing_file_raises(self):
        loader = CustomDatasetLoader()
        with pytest.raises(FileNotFoundError, match="Dataset file not found"):
            loader.load("/nonexistent/path/custom.jsonl")


# ---------------------------------------------------------------------------
# 6. ValueError when path is a directory, not a file
# ---------------------------------------------------------------------------


class TestPathIsDirectory:
    """All loaders raise ValueError when given a directory path."""

    def test_swe_bench_directory_raises(self, tmp_path):
        loader = SweBenchLoader()
        with pytest.raises(ValueError, match="Path is not a file"):
            loader.load(str(tmp_path))

    def test_aacr_bench_directory_raises(self, tmp_path):
        loader = AacrBenchLoader()
        with pytest.raises(ValueError, match="Path is not a file"):
            loader.load(str(tmp_path))

    def test_custom_directory_raises(self, tmp_path):
        loader = CustomDatasetLoader()
        with pytest.raises(ValueError, match="Path is not a file"):
            loader.load(str(tmp_path))
