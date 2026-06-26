"""Pytest 全局配置和 fixtures。"""

import pytest


@pytest.fixture
def sample_task_data() -> dict:
    """示例任务数据。"""
    return {
        "task_id": "test-001",
        "source": "custom",
        "category": "bug_fix",
        "difficulty": "easy",
        "language": "python",
        "input": {"description": "Fix the bug in function add()"},
        "ground_truth": {"expected": "def add(a, b): return a + b"},
    }
