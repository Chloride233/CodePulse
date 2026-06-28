"""Pytest 全局配置和 fixtures。"""

import pytest

try:
    import docker

    _docker_available = docker.from_env().ping()
except Exception:
    _docker_available = False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """自动跳过需要 Docker 但 Docker 不可用的集成测试。"""
    if _docker_available:
        return
    skip_integration = pytest.mark.skip(reason="Docker daemon 不可用")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


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
        "ground_truth": {"expected_output": "def add(a, b): return a + b"},
    }
