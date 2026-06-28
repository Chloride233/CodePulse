"""Docker 沙箱管理器。

提供容器生命周期管理：创建、执行、快照、回滚、销毁。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import docker
from docker.errors import APIError, ImageNotFound, NotFound

if TYPE_CHECKING:
    from docker.models.containers import Container as DockerContainer

logger = logging.getLogger(__name__)


class SandboxError(Exception):
    """沙箱操作失败时抛出。"""


@dataclass(frozen=True)
class ResourceLimits:
    """容器资源限制。"""

    cpu_count: int = 2
    memory_mb: int = 2048
    timeout_seconds: int = 300


@dataclass(frozen=True)
class Container:
    """容器句柄。"""

    id: str
    image: str
    resource_limits: ResourceLimits


@dataclass(frozen=True)
class ExecutionResult:
    """命令执行结果。"""

    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class Snapshot:
    """容器快照。"""

    container_id: str
    image_tag: str


class SandboxManager:
    """Docker 沙箱管理器。

    每个评测任务使用独立容器，确保环境隔离。

    Usage::

        manager = SandboxManager()
        container = manager.create("python:3.11-slim")
        result = manager.execute(container, "python -c 'print(1+1)'")
        snap = manager.snapshot(container)
        manager.destroy(container)

        restored = manager.restore(snap)
        manager.destroy(restored)

    工具绑定：:meth:`set_active_container` / :meth:`get_active_container`
    允许工具系统在 Agent 执行期间访问当前容器，避免 monkey-patching。
    """

    def __init__(self, base_url: str | None = None) -> None:
        """初始化沙箱管理器。

        Args:
            base_url: Docker daemon 地址，默认使用本地 socket。

        Raises:
            SandboxError: 无法连接 Docker daemon。
        """
        try:
            self._client = docker.DockerClient(base_url=base_url)
            self._client.ping()
        except Exception as exc:
            raise SandboxError(f"无法连接 Docker daemon: {exc}") from exc
        self._active_container: Container | None = None

    # ------------------------------------------------------------------
    # 活跃容器绑定 — 工具系统通过此 API 访问当前容器
    # ------------------------------------------------------------------

    def set_active_container(self, container: Container) -> None:
        """设置当前活跃容器，供工具系统使用。

        在 Agent 执行前调用此方法绑定容器，执行后解绑。
        避免工具代码直接 monkey-patch 私有属性。

        Args:
            container: 当前活跃的容器句柄。
        """
        self._active_container = container

    def get_active_container(self) -> Container:
        """获取当前活跃容器。

        Returns:
            当前活跃的容器句柄。

        Raises:
            SandboxError: 未设置活跃容器时调用。
        """
        if self._active_container is None:
            raise SandboxError("未设置活跃容器，请先调用 set_active_container()")
        return self._active_container

    def clear_active_container(self) -> None:
        """清除活跃容器绑定。"""
        self._active_container = None

    def create(
        self,
        image: str,
        resource_limits: ResourceLimits | None = None,
    ) -> Container:
        """创建新容器。

        拉取镜像（如本地不存在），然后创建并启动容器。
        容器以 detached 模式运行 ``sleep infinity``，保持存活直到销毁。

        Args:
            image: Docker 镜像名称（含 tag，如 ``python:3.11-slim``）。
            resource_limits: 资源限制配置，默认使用 ``ResourceLimits()``。

        Returns:
            Container 句柄。

        Raises:
            SandboxError: 镜像拉取失败或容器创建失败。
        """
        limits = resource_limits or ResourceLimits()
        self._ensure_image(image)

        try:
            docker_container: DockerContainer = self._client.containers.run(
                image=image,
                command=["sleep", "infinity"],
                detach=True,
                nano_cpus=limits.cpu_count * 1_000_000_000,
                mem_limit=f"{limits.memory_mb}m",
                network_disabled=True,
                read_only=False,
                # tmpfs mounts so read-only rootfs doesn't break most programs
                tmpfs={"/tmp": "size=256m"},  # nosec B108 — container-internal tmpfs, not host path
            )
        except APIError as exc:
            raise SandboxError(f"创建容器失败: {exc}") from exc

        logger.info("容器已创建: %s (image=%s)", docker_container.short_id, image)
        return Container(
            id=docker_container.id,
            image=image,
            resource_limits=limits,
        )

    def execute(self, container: Container, command: str) -> ExecutionResult:
        """在容器中执行命令。

        使用 docker exec 在运行中的容器内执行命令，返回执行结果。

        Args:
            container: 目标容器句柄。
            command: 要执行的 shell 命令。

        Returns:
            执行结果，包含 exit_code、stdout、stderr。

        Raises:
            SandboxError: 容器不存在或执行超时。
        """
        docker_container = self._get_container(container.id)

        try:
            exit_code, output = docker_container.exec_run(
                cmd=["sh", "-c", command],
                demux=True,
            )
        except Exception as exc:
            raise SandboxError(f"命令执行失败: {exc}") from exc

        stdout_bytes, stderr_bytes = output or (None, None)
        return ExecutionResult(
            exit_code=exit_code,
            stdout=(stdout_bytes or b"").decode("utf-8", errors="replace"),
            stderr=(stderr_bytes or b"").decode("utf-8", errors="replace"),
        )

    def snapshot(self, container: Container) -> Snapshot:
        """创建容器快照。

        将当前容器状态 commit 为一个新的 Docker 镜像。

        Args:
            container: 目标容器句柄。

        Returns:
            Snapshot 句柄，包含快照镜像 tag。

        Raises:
            SandboxError: 容器不存在或 commit 失败。
        """
        docker_container = self._get_container(container.id)
        tag = f"codepulse/snapshot-{uuid.uuid4().hex[:12]}"

        try:
            docker_container.commit(repository=tag)
        except APIError as exc:
            raise SandboxError(f"快照创建失败: {exc}") from exc

        logger.info("快照已创建: %s -> %s", container.id[:12], tag)
        return Snapshot(container_id=container.id, image_tag=tag)

    def restore(self, snapshot: Snapshot) -> Container:
        """从快照恢复容器。

        基于快照镜像创建并启动一个新容器，资源限制与原容器相同。

        Args:
            snapshot: 快照句柄。

        Returns:
            恢复后的 Container 句柄。

        Raises:
            SandboxError: 快照镜像不存在或容器创建失败。
        """
        try:
            self._client.images.get(snapshot.image_tag)
        except ImageNotFound as exc:
            raise SandboxError(f"快照镜像不存在: {snapshot.image_tag}") from exc

        try:
            docker_container: DockerContainer = self._client.containers.run(
                image=snapshot.image_tag,
                command=["sleep", "infinity"],
                detach=True,
            )
        except APIError as exc:
            raise SandboxError(f"从快照恢复容器失败: {exc}") from exc

        logger.info("容器已从快照恢复: %s -> %s", snapshot.image_tag, docker_container.short_id)
        return Container(
            id=docker_container.id,
            image=snapshot.image_tag,
            resource_limits=ResourceLimits(),
        )

    def destroy(self, container: Container) -> None:
        """销毁容器。

        停止并删除容器，清理资源。

        Args:
            container: 要销毁的容器句柄。

        Raises:
            SandboxError: 容器操作失败（已不存在时静默成功）。
        """
        try:
            docker_container = self._client.containers.get(container.id)
        except NotFound:
            logger.warning("容器已不存在，跳过销毁: %s", container.id[:12])
            return

        try:
            docker_container.stop(timeout=5)
        except (APIError, NotFound) as exc:
            logger.warning("停止容器时出错（忽略）: %s", exc)

        try:
            docker_container.remove(force=True)
        except (APIError, NotFound) as exc:
            raise SandboxError(f"删除容器失败: {exc}") from exc

        logger.info("容器已销毁: %s", container.id[:12])

    def _ensure_image(self, image: str) -> None:
        """确保镜像存在于本地，不存在则拉取。

        Args:
            image: 镜像名称。

        Raises:
            SandboxError: 拉取失败。
        """
        try:
            self._client.images.get(image)
            return
        except ImageNotFound:
            pass

        logger.info("正在拉取镜像: %s", image)
        try:
            self._client.images.pull(image)
        except APIError as exc:
            raise SandboxError(f"镜像拉取失败 ({image}): {exc}") from exc

    def _get_container(self, container_id: str) -> DockerContainer:
        """获取运行中的容器对象。

        Args:
            container_id: 容器 ID。

        Returns:
            Docker SDK Container 对象。

        Raises:
            SandboxError: 容器不存在。
        """
        try:
            return self._client.containers.get(container_id)
        except NotFound as exc:
            raise SandboxError(f"容器不存在: {container_id[:12]}") from exc
