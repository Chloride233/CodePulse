"""codepulse.env.sandbox 测试。

单元测试使用 mock 隔离 Docker daemon，纯确定性。
集成测试（@pytest.mark.integration）需要真实 Docker daemon。
运行方式：
    pytest tests/test_sandbox.py                    # 仅单元测试
    pytest tests/test_sandbox.py -m integration     # 仅集成测试
    pytest tests/test_sandbox.py -m "not integration"  # 排除集成测试
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from docker.errors import APIError, ImageNotFound, NotFound

from codepulse.env.sandbox import (
    Container,
    ExecutionResult,
    ResourceLimits,
    SandboxError,
    SandboxManager,
    Snapshot,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_docker():
    """Patch docker.DockerClient 并返回 (client_cls, client_instance)。"""
    with patch("codepulse.env.sandbox.docker") as mock_mod:
        client_instance = MagicMock()
        mock_mod.DockerClient.return_value = client_instance
        yield mock_mod, client_instance


@pytest.fixture
def manager(mock_docker) -> SandboxManager:
    """已连接的 SandboxManager。"""
    return SandboxManager()


@pytest.fixture
def sample_container() -> Container:
    """示例 Container 句柄。"""
    return Container(
        id="abc123def456",
        image="python:3.11-slim",
        resource_limits=ResourceLimits(cpu_count=2, memory_mb=2048, timeout_seconds=300),
    )


@pytest.fixture
def sample_snapshot() -> Snapshot:
    """示例 Snapshot 句柄。"""
    return Snapshot(container_id="abc123def456", image_tag="codepulse/snapshot-abc123def456")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class TestResourceLimits:
    """ResourceLimits 数据类测试。"""

    def test_defaults(self):
        limits = ResourceLimits()
        assert limits.cpu_count == 2
        assert limits.memory_mb == 2048
        assert limits.timeout_seconds == 300

    def test_custom_values(self):
        limits = ResourceLimits(cpu_count=4, memory_mb=4096, timeout_seconds=600)
        assert limits.cpu_count == 4
        assert limits.memory_mb == 4096
        assert limits.timeout_seconds == 600

    def test_frozen(self):
        limits = ResourceLimits()
        with pytest.raises(AttributeError):
            limits.cpu_count = 8  # type: ignore[misc]


class TestContainer:
    """Container 数据类测试。"""

    def test_fields(self, sample_container):
        assert sample_container.id == "abc123def456"
        assert sample_container.image == "python:3.11-slim"
        assert isinstance(sample_container.resource_limits, ResourceLimits)

    def test_frozen(self, sample_container):
        with pytest.raises(AttributeError):
            sample_container.id = "new"  # type: ignore[misc]


class TestExecutionResult:
    """ExecutionResult 数据类测试。"""

    def test_fields(self):
        result = ExecutionResult(exit_code=0, stdout="ok", stderr="")
        assert result.exit_code == 0
        assert result.stdout == "ok"
        assert result.stderr == ""

    def test_frozen(self):
        result = ExecutionResult(exit_code=0, stdout="", stderr="")
        with pytest.raises(AttributeError):
            result.exit_code = 1  # type: ignore[misc]


class TestSnapshot:
    """Snapshot 数据类测试。"""

    def test_fields(self, sample_snapshot):
        assert sample_snapshot.container_id == "abc123def456"
        assert "snapshot" in sample_snapshot.image_tag

    def test_frozen(self, sample_snapshot):
        with pytest.raises(AttributeError):
            sample_snapshot.image_tag = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SandboxError
# ---------------------------------------------------------------------------


class TestSandboxError:
    """SandboxError 异常测试。"""

    def test_is_exception(self):
        assert issubclass(SandboxError, Exception)

    def test_message(self):
        err = SandboxError("something broke")
        assert str(err) == "something broke"


# ---------------------------------------------------------------------------
# SandboxManager.__init__
# ---------------------------------------------------------------------------


class TestSandboxManagerInit:
    """SandboxManager 初始化测试。"""

    def test_success(self, mock_docker):
        _, client = mock_docker
        client.ping.return_value = True
        mgr = SandboxManager()
        assert mgr._client is client
        client.ping.assert_called_once()

    def test_connection_failure(self, mock_docker):
        _, client = mock_docker
        client.ping.side_effect = OSError("no socket")
        with pytest.raises(SandboxError, match="无法连接 Docker daemon"):
            SandboxManager()

    def test_custom_base_url(self, mock_docker):
        mock_mod, client = mock_docker
        client.ping.return_value = True
        SandboxManager(base_url="tcp://remote:2375")
        mock_mod.DockerClient.assert_called_with(base_url="tcp://remote:2375")


# ---------------------------------------------------------------------------
# SandboxManager.create
# ---------------------------------------------------------------------------


class TestSandboxManagerCreate:
    """create() 方法测试。"""

    def test_create_success(self, manager, mock_docker):
        _, client = mock_docker
        # Image exists locally
        client.images.get.return_value = MagicMock()
        # Container run returns a mock
        mock_ctr = MagicMock()
        mock_ctr.id = "aaa111"
        mock_ctr.short_id = "aaa111"
        client.containers.run.return_value = mock_ctr

        container = manager.create("python:3.11-slim")

        assert container.id == "aaa111"
        assert container.image == "python:3.11-slim"
        assert container.resource_limits == ResourceLimits()
        client.containers.run.assert_called_once()
        call_kwargs = client.containers.run.call_args
        assert call_kwargs.kwargs["detach"] is True
        assert call_kwargs.kwargs["network_disabled"] is True
        assert call_kwargs.kwargs["nano_cpus"] == 2_000_000_000
        assert call_kwargs.kwargs["mem_limit"] == "2048m"

    def test_create_with_custom_limits(self, manager, mock_docker):
        _, client = mock_docker
        client.images.get.return_value = MagicMock()
        mock_ctr = MagicMock()
        mock_ctr.id = "bbb222"
        client.containers.run.return_value = mock_ctr

        limits = ResourceLimits(cpu_count=4, memory_mb=4096)
        container = manager.create("ubuntu:22.04", resource_limits=limits)

        assert container.resource_limits.cpu_count == 4
        assert container.resource_limits.memory_mb == 4096
        call_kwargs = client.containers.run.call_args
        assert call_kwargs.kwargs["nano_cpus"] == 4_000_000_000
        assert call_kwargs.kwargs["mem_limit"] == "4096m"

    def test_create_pulls_image_if_missing(self, manager, mock_docker):
        _, client = mock_docker
        client.images.get.side_effect = ImageNotFound("nope")
        client.images.pull.return_value = MagicMock()
        mock_ctr = MagicMock()
        mock_ctr.id = "ccc333"
        client.containers.run.return_value = mock_ctr

        container = manager.create("alpine:latest")
        assert container.id == "ccc333"
        client.images.pull.assert_called_once_with("alpine:latest")

    def test_create_pull_failure(self, manager, mock_docker):
        _, client = mock_docker
        client.images.get.side_effect = ImageNotFound("nope")
        client.images.pull.side_effect = APIError("pull failed")

        with pytest.raises(SandboxError, match="镜像拉取失败"):
            manager.create("bad-image:nope")

    def test_create_container_run_failure(self, manager, mock_docker):
        _, client = mock_docker
        client.images.get.return_value = MagicMock()
        client.containers.run.side_effect = APIError("run failed")

        with pytest.raises(SandboxError, match="创建容器失败"):
            manager.create("python:3.11-slim")


# ---------------------------------------------------------------------------
# SandboxManager.execute
# ---------------------------------------------------------------------------


class TestSandboxManagerExecute:
    """execute() 方法测试。"""

    def test_execute_success(self, manager, mock_docker, sample_container):
        _, client = mock_docker
        mock_ctr = MagicMock()
        mock_ctr.exec_run.return_value = (0, (b"hello world\n", b""))
        client.containers.get.return_value = mock_ctr

        result = manager.execute(sample_container, "echo hello world")

        assert result.exit_code == 0
        assert result.stdout == "hello world\n"
        assert result.stderr == ""
        mock_ctr.exec_run.assert_called_once_with(
            cmd=["sh", "-c", "echo hello world"],
            demux=True,
        )

    def test_execute_with_stderr(self, manager, mock_docker, sample_container):
        _, client = mock_docker
        mock_ctr = MagicMock()
        mock_ctr.exec_run.return_value = (1, (b"", b"error occurred\n"))
        client.containers.get.return_value = mock_ctr

        result = manager.execute(sample_container, "exit 1")
        assert result.exit_code == 1
        assert result.stdout == ""
        assert result.stderr == "error occurred\n"

    def test_execute_nonzero_exit(self, manager, mock_docker, sample_container):
        _, client = mock_docker
        mock_ctr = MagicMock()
        mock_ctr.exec_run.return_value = (127, (b"", b"command not found\n"))
        client.containers.get.return_value = mock_ctr

        result = manager.execute(sample_container, "nonexistent-cmd")
        assert result.exit_code == 127
        assert "command not found" in result.stderr

    def test_execute_container_not_found(self, manager, mock_docker, sample_container):
        _, client = mock_docker
        client.containers.get.side_effect = NotFound("gone")

        with pytest.raises(SandboxError, match="容器不存在"):
            manager.execute(sample_container, "ls")

    def test_execute_timeout(self, manager, mock_docker, sample_container):
        _, client = mock_docker
        mock_ctr = MagicMock()
        mock_ctr.exec_run.side_effect = Exception("timeout")
        client.containers.get.return_value = mock_ctr

        with pytest.raises(SandboxError, match="命令执行失败"):
            manager.execute(sample_container, "sleep 999")

    def test_execute_demux_none_output(self, manager, mock_docker, sample_container):
        """exec_run 可能返回 None output。"""
        _, client = mock_docker
        mock_ctr = MagicMock()
        mock_ctr.exec_run.return_value = (0, None)
        client.containers.get.return_value = mock_ctr

        result = manager.execute(sample_container, "true")
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""


# ---------------------------------------------------------------------------
# SandboxManager.snapshot
# ---------------------------------------------------------------------------


class TestSandboxManagerSnapshot:
    """snapshot() 方法测试。"""

    def test_snapshot_success(self, manager, mock_docker, sample_container):
        _, client = mock_docker
        mock_ctr = MagicMock()
        client.containers.get.return_value = mock_ctr

        snap = manager.snapshot(sample_container)

        assert snap.container_id == sample_container.id
        assert snap.image_tag.startswith("codepulse/snapshot-")
        mock_ctr.commit.assert_called_once()

    def test_snapshot_container_not_found(self, manager, mock_docker, sample_container):
        _, client = mock_docker
        client.containers.get.side_effect = NotFound("gone")

        with pytest.raises(SandboxError, match="容器不存在"):
            manager.snapshot(sample_container)

    def test_snapshot_commit_failure(self, manager, mock_docker, sample_container):
        _, client = mock_docker
        mock_ctr = MagicMock()
        mock_ctr.commit.side_effect = APIError("commit failed")
        client.containers.get.return_value = mock_ctr

        with pytest.raises(SandboxError, match="快照创建失败"):
            manager.snapshot(sample_container)


# ---------------------------------------------------------------------------
# SandboxManager.restore
# ---------------------------------------------------------------------------


class TestSandboxManagerRestore:
    """restore() 方法测试。"""

    def test_restore_success(self, manager, mock_docker, sample_snapshot):
        _, client = mock_docker
        client.images.get.return_value = MagicMock()
        mock_ctr = MagicMock()
        mock_ctr.id = "restored-111"
        mock_ctr.short_id = "restored"
        client.containers.run.return_value = mock_ctr

        container = manager.restore(sample_snapshot)

        assert container.id == "restored-111"
        assert container.image == sample_snapshot.image_tag
        assert container.resource_limits == ResourceLimits()
        client.containers.run.assert_called_once()

    def test_restore_image_not_found(self, manager, mock_docker, sample_snapshot):
        _, client = mock_docker
        client.images.get.side_effect = ImageNotFound("no snapshot")

        with pytest.raises(SandboxError, match="快照镜像不存在"):
            manager.restore(sample_snapshot)

    def test_restore_run_failure(self, manager, mock_docker, sample_snapshot):
        _, client = mock_docker
        client.images.get.return_value = MagicMock()
        client.containers.run.side_effect = APIError("run failed")

        with pytest.raises(SandboxError, match="从快照恢复容器失败"):
            manager.restore(sample_snapshot)


# ---------------------------------------------------------------------------
# SandboxManager.destroy
# ---------------------------------------------------------------------------


class TestSandboxManagerDestroy:
    """destroy() 方法测试。"""

    def test_destroy_success(self, manager, mock_docker, sample_container):
        _, client = mock_docker
        mock_ctr = MagicMock()
        client.containers.get.return_value = mock_ctr

        manager.destroy(sample_container)

        mock_ctr.stop.assert_called_once_with(timeout=5)
        mock_ctr.remove.assert_called_once_with(force=True)

    def test_destroy_already_removed(self, manager, mock_docker, sample_container):
        """容器已不存在时静默成功。"""
        _, client = mock_docker
        client.containers.get.side_effect = NotFound("gone")

        # Should not raise
        manager.destroy(sample_container)

    def test_destroy_stop_error_ignored(self, manager, mock_docker, sample_container):
        """stop 失败时继续 remove。"""
        _, client = mock_docker
        mock_ctr = MagicMock()
        mock_ctr.stop.side_effect = APIError("stop failed")
        client.containers.get.return_value = mock_ctr

        manager.destroy(sample_container)

        mock_ctr.remove.assert_called_once_with(force=True)

    def test_destroy_remove_failure(self, manager, mock_docker, sample_container):
        """remove 失败时抛出 SandboxError。"""
        _, client = mock_docker
        mock_ctr = MagicMock()
        mock_ctr.remove.side_effect = APIError("remove failed")
        client.containers.get.return_value = mock_ctr

        with pytest.raises(SandboxError, match="删除容器失败"):
            manager.destroy(sample_container)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


class TestEnsureImage:
    """_ensure_image() 测试。"""

    def test_image_exists(self, manager, mock_docker):
        _, client = mock_docker
        client.images.get.return_value = MagicMock()
        manager._ensure_image("python:3.11")
        client.images.pull.assert_not_called()

    def test_image_missing_pulls(self, manager, mock_docker):
        _, client = mock_docker
        client.images.get.side_effect = ImageNotFound("nope")
        client.images.pull.return_value = MagicMock()
        manager._ensure_image("alpine:latest")
        client.images.pull.assert_called_once_with("alpine:latest")

    def test_pull_failure_raises(self, manager, mock_docker):
        _, client = mock_docker
        client.images.get.side_effect = ImageNotFound("nope")
        client.images.pull.side_effect = APIError("pull err")
        with pytest.raises(SandboxError, match="镜像拉取失败"):
            manager._ensure_image("bad:tag")


class TestGetContainer:
    """_get_container() 测试。"""

    def test_found(self, manager, mock_docker):
        _, client = mock_docker
        mock_ctr = MagicMock()
        client.containers.get.return_value = mock_ctr
        assert manager._get_container("abc123") is mock_ctr

    def test_not_found(self, manager, mock_docker):
        _, client = mock_docker
        client.containers.get.side_effect = NotFound("gone")
        with pytest.raises(SandboxError, match="容器不存在"):
            manager._get_container("abc123")


# ---------------------------------------------------------------------------
# Integration tests — require a running Docker daemon
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSandboxManagerIntegration:
    """集成测试：需要真实 Docker daemon。

    运行方式: pytest -m integration
    """

    IMAGE = "alpine:3.19"

    @pytest.fixture
    def real_manager(self):
        """真实 SandboxManager（不 mock）。"""
        mgr = SandboxManager()
        yield mgr

    def test_create_and_destroy(self, real_manager):
        """创建并销毁容器。"""
        container = real_manager.create(self.IMAGE)
        assert container.image == self.IMAGE
        assert container.resource_limits == ResourceLimits()
        real_manager.destroy(container)

    def test_execute_echo(self, real_manager):
        """在容器中执行 echo 命令。"""
        container = real_manager.create(self.IMAGE)
        try:
            result = real_manager.execute(container, "echo hello")
            assert result.exit_code == 0
            assert "hello" in result.stdout
        finally:
            real_manager.destroy(container)

    def test_execute_failing_command(self, real_manager):
        """执行失败命令返回非零 exit code。"""
        container = real_manager.create(self.IMAGE)
        try:
            result = real_manager.execute(container, "ls /nonexistent_path_xyz")
            assert result.exit_code != 0
            assert result.stderr != ""
        finally:
            real_manager.destroy(container)

    def test_snapshot_and_restore(self, real_manager):
        """快照和恢复容器。"""
        container = real_manager.create(self.IMAGE)
        try:
            # Create a file so we can verify it survives snapshot
            real_manager.execute(container, "touch /snapshot_marker")
            snap = real_manager.snapshot(container)
            assert snap.container_id == container.id
            assert "snapshot" in snap.image_tag

            restored = real_manager.restore(snap)
            try:
                result = real_manager.execute(restored, "ls /snapshot_marker")
                assert result.exit_code == 0
            finally:
                real_manager.destroy(restored)
        finally:
            real_manager.destroy(container)

    def test_destroy_nonexistent_container(self, real_manager):
        """销毁不存在的容器不抛异常。"""
        fake = Container(
            id="nonexistent-id-1234567890ab",
            image="alpine:3.19",
            resource_limits=ResourceLimits(),
        )
        # Should not raise
        real_manager.destroy(fake)

    def test_create_with_custom_resource_limits(self, real_manager):
        """使用自定义资源限制创建容器。"""
        limits = ResourceLimits(cpu_count=1, memory_mb=512, timeout_seconds=60)
        container = real_manager.create(self.IMAGE, resource_limits=limits)
        try:
            assert container.resource_limits == limits
        finally:
            real_manager.destroy(container)
