"""Tests for codepulse.env.sandbox_utils module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from codepulse.env.sandbox_utils import PytestResult, SandboxUtils


class TestPytestResult:
    """Tests for PytestResult dataclass."""

    def test_pass_rate_all_passed(self) -> None:
        result = PytestResult(
            total=10, passed=10, failed=0, errors=0, skipped=0,
            exit_code=0, stdout="", stderr="",
        )
        assert result.pass_rate == 1.0

    def test_pass_rate_partial(self) -> None:
        result = PytestResult(
            total=10, passed=7, failed=3, errors=0, skipped=0,
            exit_code=1, stdout="", stderr="",
        )
        assert result.pass_rate == 0.7

    def test_pass_rate_zero_total(self) -> None:
        result = PytestResult(
            total=0, passed=0, failed=0, errors=0, skipped=0,
            exit_code=0, stdout="", stderr="",
        )
        assert result.pass_rate == 0.0


class TestSandboxUtilsWriteFile:
    """Tests for SandboxUtils.write_file."""

    @patch("codepulse.env.sandbox_utils.tarfile")
    def test_write_file_calls_put_archive(self, mock_tarfile: MagicMock) -> None:
        sandbox = MagicMock()
        container = MagicMock()
        container.id = "test-container"
        utils = SandboxUtils(sandbox)

        # Mock the Docker client
        mock_docker_container = MagicMock()
        sandbox._client.containers.get.return_value = mock_docker_container

        utils.write_file(container, "test.py", "print('hello')")

        # 验证 mkdir -p 被调用
        sandbox.execute.assert_called_once_with(container, "mkdir -p /workspace")
        # 验证 put_archive 被调用
        mock_docker_container.put_archive.assert_called_once()


class TestSandboxUtilsReadFile:
    """Tests for SandboxUtils.read_file."""

    def test_read_file_success(self) -> None:
        sandbox = MagicMock()
        container = MagicMock()
        exec_result = MagicMock()
        exec_result.exit_code = 0
        exec_result.stdout = "file content"
        exec_result.stderr = ""
        sandbox.execute.return_value = exec_result

        utils = SandboxUtils(sandbox)
        content = utils.read_file(container, "test.py")
        assert content == "file content"

    def test_read_file_not_found(self) -> None:
        from codepulse.env.sandbox import SandboxError

        sandbox = MagicMock()
        container = MagicMock()
        exec_result = MagicMock()
        exec_result.exit_code = 1
        exec_result.stderr = "No such file"
        sandbox.execute.return_value = exec_result

        utils = SandboxUtils(sandbox)
        with pytest.raises(SandboxError):
            utils.read_file(container, "nonexistent.py")


class TestSandboxUtilsSetupWorkspace:
    """Tests for SandboxUtils.setup_workspace."""

    @patch("codepulse.env.sandbox_utils.tarfile")
    def test_setup_workspace_writes_multiple_files(self, mock_tarfile: MagicMock) -> None:
        sandbox = MagicMock()
        container = MagicMock()
        container.id = "test-container"
        mock_docker_container = MagicMock()
        sandbox._client.containers.get.return_value = mock_docker_container

        utils = SandboxUtils(sandbox)
        utils.setup_workspace(container, {
            "a.py": "content a",
            "b.py": "content b",
        })

        # 两次 mkdir + 两次 put_archive
        assert sandbox.execute.call_count == 2
        assert mock_docker_container.put_archive.call_count == 2
