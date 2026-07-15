"""沙箱工具函数 — 文件操作和测试执行。

在 SandboxManager 之上提供高层操作：写入文件、读取文件、运行 pytest。
"""

from __future__ import annotations

import io
import json
import logging
import shlex
import tarfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codepulse.env.sandbox import Container, SandboxManager

logger = logging.getLogger(__name__)


def _workspace_relative_path(path: str) -> str:
    """Normalize a relative or /workspace path and reject traversal."""
    normalized = path.strip()
    if normalized.startswith("/workspace/"):
        normalized = normalized.removeprefix("/workspace/")
    candidate = PurePosixPath(normalized)
    if not normalized or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Path must stay inside /workspace: {path}")
    return candidate.as_posix()


@dataclass(frozen=True)
class PytestResult:
    """pytest JSON 报告解析结果。"""

    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    exit_code: int
    stdout: str
    stderr: str

    @property
    def pass_rate(self) -> float:
        """通过率（0-1）。"""
        return self.passed / self.total if self.total > 0 else 0.0


class SandboxUtils:
    """沙箱工具函数集合。

    Usage::

        utils = SandboxUtils(sandbox)
        utils.write_file(container, "solution.py", code)
        result = utils.run_pytest(container, "test_solution.py")
    """

    def __init__(self, sandbox: SandboxManager) -> None:
        self._sandbox = sandbox

    def write_file(self, container: Container, path: str, content: str) -> None:
        """写入文件到容器。

        通过 tar 归档 + put_archive 实现，自动创建父目录。

        Args:
            container: 目标容器。
            path: 容器内文件路径（相对于 /workspace）。
            content: 文件内容。

        Raises:
            SandboxError: 写入失败。
        """
        relative_path = _workspace_relative_path(path)

        # 确保工作目录存在
        self._sandbox.execute(container, "mkdir -p /workspace")

        # 构建 tar 归档
        tar_data = io.BytesIO()
        with tarfile.open(fileobj=tar_data, mode="w") as tar:
            content_bytes = content.encode("utf-8")
            info = tarfile.TarInfo(name=relative_path)
            info.size = len(content_bytes)
            tar.addfile(info, io.BytesIO(content_bytes))

        tar_data.seek(0)

        # 通过 Docker API 写入
        try:
            docker_container = self._sandbox._client.containers.get(container.id)
            docker_container.put_archive("/workspace", tar_data.read())
        except Exception as exc:
            from codepulse.env.sandbox import SandboxError

            raise SandboxError(f"写入文件失败 ({path}): {exc}") from exc

        logger.debug("文件已写入: %s (%d bytes)", path, len(content))

    def read_file(self, container: Container, path: str) -> str:
        """从容器读取文件。

        Args:
            container: 目标容器。
            path: 容器内文件路径。

        Returns:
            文件内容。

        Raises:
            SandboxError: 读取失败。
        """
        relative_path = _workspace_relative_path(path)
        workspace_path = shlex.quote(f"/workspace/{relative_path}")
        result = self._sandbox.execute(container, f"cat {workspace_path}")
        if result.exit_code != 0:
            from codepulse.env.sandbox import SandboxError

            raise SandboxError(f"读取文件失败 ({path}): {result.stderr}")
        return result.stdout

    def run_pytest(
        self,
        container: Container,
        test_path: str = "",
        timeout: int = 60,
    ) -> PytestResult:
        """运行 pytest 并解析 JSON 报告。

        Args:
            container: 目标容器。
            test_path: 测试文件路径（相对于 /workspace），空则运行全部。
            timeout: 超时秒数。

        Returns:
            PytestResult 解析结果。
        """
        # 确保 pytest 和 pytest-json-report 已安装
        self._sandbox.execute(container, "pip install pytest pytest-json-report -q 2>/dev/null")

        # 运行 pytest，生成 JSON 报告
        report_path = "/tmp/pytest_report.json"  # nosec B108 — container-internal path, not host
        cmd_parts = [
            "cd /workspace &&",
            "python -m pytest",
            test_path,
            f"--json-report --json-report-file={report_path}",
            "--tb=short -q",
            f"--timeout={timeout}" if timeout else "",
            "2>&1",
        ]
        cmd = " ".join(p for p in cmd_parts if p)
        result = self._sandbox.execute(container, cmd)

        # 读取 JSON 报告
        report_result = self._sandbox.execute(container, f"cat {report_path}")
        if report_result.exit_code == 0 and report_result.stdout.strip():
            try:
                report = json.loads(report_result.stdout)
                summary = report.get("summary", {})
                return PytestResult(
                    total=summary.get("total", 0),
                    passed=summary.get("passed", 0),
                    failed=summary.get("failed", 0),
                    errors=summary.get("error", 0),
                    skipped=summary.get("skipped", 0),
                    exit_code=result.exit_code,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
            except json.JSONDecodeError:
                pass

        # JSON 报告不可用，退化为 exit code 判断
        return PytestResult(
            total=1 if result.exit_code == 0 else 0,
            passed=1 if result.exit_code == 0 else 0,
            failed=0 if result.exit_code == 0 else 1,
            errors=0,
            skipped=0,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def setup_workspace(
        self,
        container: Container,
        task_files: dict[str, str],
    ) -> None:
        """批量写入任务文件到工作区。

        Args:
            container: 目标容器。
            task_files: 文件路径到内容的映射。
        """
        for path, content in task_files.items():
            self.write_file(container, path, content)
