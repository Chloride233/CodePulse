"""Agent 适配器系统 — 零侵入接入用户的 Agent。

支持三种接入方式：
1. CLI 模式：执行用户命令，零侵入
2. Protocol 模式：Python 类实现 Agent Protocol
3. Mock 模式：不调用 LLM，测试管线用

核心理念：Agent 不需要知道 CodePulse 的存在。
框架负责：注入任务 → 执行 Agent → 采集结果 → 评分。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from codepulse.eval.scoring import PASS_THRESHOLD, ScoreDimension

if TYPE_CHECKING:
    from codepulse.data.models import Task
    from codepulse.env.sandbox import Container, SandboxManager
    from codepulse.shared.trace_types import Transcript

logger = logging.getLogger(__name__)


# ======================================================================
# Agent 配置
# ======================================================================


@dataclass(frozen=True)
class AgentProfile:
    """Agent 配置文件 — 描述一个完整的 Agent。

    从 YAML 文件加载，也可以直接构造。
    """

    name: str
    type: str  # "protocol" | "cli" | "mock"
    model: str = ""

    # CLI 模式配置
    command: str = ""  # 启动命令，支持 {task_file} 占位符
    workdir: str = "/workspace"
    timeout: int = 300

    # Protocol 模式配置
    agent_class: str = ""  # "module.ClassName"

    # 工具配置
    system_prompt: str = ""
    tools: list[str] = field(default_factory=lambda: ["read_file", "write_file", "execute"])
    max_iterations: int = 20
    temperature: float = 0.0
    max_tokens: int = 4096

    # 元信息
    description: str = ""
    version: str = "1.0"
    author: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> AgentProfile:
        """从 YAML 文件加载 Agent 配置。"""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Agent 配置文件不存在: {path}")

        with file_path.open(encoding="utf-8") as fh:
            data: dict[str, Any] = yaml.safe_load(fh) or {}

        return cls(
            name=data.get("name", file_path.stem),
            type=data.get("type", "protocol"),
            model=data.get("model", ""),
            command=data.get("command", ""),
            workdir=data.get("workdir", "/workspace"),
            timeout=data.get("timeout", 300),
            agent_class=data.get("agent_class", ""),
            system_prompt=data.get("system_prompt", ""),
            tools=data.get("tools", ["read_file", "write_file", "execute"]),
            max_iterations=data.get("max_iterations", 20),
            temperature=data.get("temperature", 0.0),
            max_tokens=data.get("max_tokens", 4096),
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            author=data.get("author", ""),
            metadata=data.get("metadata", {}),
        )

    def to_yaml(self, path: str | Path) -> None:
        """保存 Agent 配置到 YAML 文件。"""
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "model": self.model,
            "description": self.description,
            "version": self.version,
        }
        if self.type == "cli":
            data["command"] = self.command
            data["workdir"] = self.workdir
            data["timeout"] = self.timeout
        elif self.type == "protocol":
            data["agent_class"] = self.agent_class
            data["system_prompt"] = self.system_prompt
            data["tools"] = self.tools
            data["max_iterations"] = self.max_iterations
            data["temperature"] = self.temperature
            data["max_tokens"] = self.max_tokens

        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False, allow_unicode=True)


# ======================================================================
# 执行结果
# ======================================================================


@dataclass
class AgentResult:
    """Agent 执行结果 — 评测的唯一输入。

    不管 Agent 用什么方式接入，最终都归一化为这个格式。
    """

    task_id: str
    exit_code: int = -1

    # 文件产出
    output_files: dict[str, str] = field(default_factory=dict)

    # 执行信息
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0

    # Trace
    transcript: Transcript | None = None

    # Token 消耗
    token_usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0

    # 元信息
    metadata: dict[str, Any] = field(default_factory=dict)


# ======================================================================
# 适配器
# ======================================================================


def run_agent(
    profile: AgentProfile,
    task: Task,
    sandbox: SandboxManager,
    container: Container,
) -> AgentResult:
    """根据 AgentProfile 类型选择适配器执行 Agent。

    Args:
        profile: Agent 配置。
        task: 评测任务。
        sandbox: 沙箱管理器。
        container: 容器句柄。

    Returns:
        AgentResult 统一结果。
    """
    if profile.type == "cli":
        return _run_cli_agent(profile, task, sandbox, container)
    elif profile.type == "protocol":
        return _run_protocol_agent(profile, task, sandbox, container)
    elif profile.type == "mock":
        return _run_mock_agent(profile, task, sandbox, container)
    else:
        return AgentResult(
            task_id=task.task_id,
            exit_code=-1,
            stderr=f"未知的 Agent 类型: {profile.type}",
        )


# ======================================================================
# CLI 适配器（零侵入）
# ======================================================================


def _run_cli_agent(
    profile: AgentProfile,
    task: Task,
    sandbox: SandboxManager,
    container: Container,
) -> AgentResult:
    """CLI 模式：执行用户的命令，零侵入。

    流程：
    1. 注入 task.json 到容器
    2. 执行用户命令
    3. 采集 stdout/stderr
    4. 收集输出文件
    """
    from codepulse.env.sandbox_utils import SandboxUtils

    utils = SandboxUtils(sandbox)
    task_id = task.task_id
    start_time = time.time()

    # 1. 注入 task.json
    task_json = _build_task_json(task)

    try:
        utils.write_file(container, "task.json", task_json)
    except Exception as exc:
        return AgentResult(
            task_id=task_id,
            exit_code=-1,
            stderr=f"注入 task.json 失败: {exc}",
            duration=time.time() - start_time,
        )

    # 2. 注入输入代码（如有）
    input_code = task.input.get("input_code", "")
    if input_code:
        filename = _guess_filename(task.language, "input")
        import contextlib
        with contextlib.suppress(Exception):
            utils.write_file(container, f"input/{filename}", input_code)

    # 3. 构建并执行命令
    command = profile.command
    if not command:
        command = "echo 'No command specified' && exit 1"

    # 替换占位符
    command = command.replace("{task_file}", f"{profile.workdir}/task.json")
    command = command.replace("{task_id}", task_id)
    command = command.replace("{language}", task.language)

    # 执行
    try:
        exec_result = sandbox.execute(container, f"cd {profile.workdir} && {command}")
    except Exception as exc:
        return AgentResult(
            task_id=task_id,
            exit_code=-1,
            stderr=f"命令执行失败: {exc}",
            duration=time.time() - start_time,
        )

    duration = time.time() - start_time

    # 4. 收集输出文件
    output_files = _collect_output_files(sandbox, container, profile.workdir)

    return AgentResult(
        task_id=task_id,
        exit_code=exec_result.exit_code,
        stdout=exec_result.stdout,
        stderr=exec_result.stderr,
        duration=duration,
        output_files=output_files,
    )


def _collect_output_files(
    sandbox: SandboxManager,
    container: Container,
    workdir: str,
) -> dict[str, str]:
    """从容器中收集输出文件。"""
    # 列出工作目录下的文件
    result = sandbox.execute(container, f"find {workdir} -type f -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.go' -o -name '*.rs' 2>/dev/null")

    files: dict[str, str] = {}
    if result.exit_code != 0:
        return files

    for line in result.stdout.strip().split("\n"):
        filepath = line.strip()
        if not filepath:
            continue
        # 读取文件内容
        cat_result = sandbox.execute(container, f"cat {filepath}")
        if cat_result.exit_code == 0:
            # 存储相对路径
            rel_path = filepath.replace(f"{workdir}/", "")
            files[rel_path] = cat_result.stdout

    return files


def _guess_filename(language: str, purpose: str = "solution") -> str:
    """根据语言猜测文件名。"""
    ext_map = {
        "python": ".py", "py": ".py",
        "javascript": ".js", "js": ".js",
        "typescript": ".ts", "ts": ".ts",
        "go": ".go", "rust": ".rs", "java": ".java",
    }
    ext = ext_map.get(language.lower(), ".txt")
    return f"{purpose}{ext}"


def _build_task_json(task: Any) -> str:
    """Construct a unified task.json string from a Task object."""
    import json as _json

    return _json.dumps(
        {
            "task_id": task.task_id,
            "description": task.input.get("description", ""),
            "input_code": task.input.get("input_code", ""),
            "expected_output": task.ground_truth.get("expected_output", ""),
            "test_cases": task.ground_truth.get("test_cases", []),
            "language": task.language,
            "category": task.category.value if hasattr(task.category, "value") else task.category,
            "difficulty": task.difficulty.value if hasattr(task.difficulty, "value") else task.difficulty,
        },
        ensure_ascii=False,
        indent=2,
    )


# ======================================================================
# Protocol 适配器
# ======================================================================


def _run_protocol_agent(
    profile: AgentProfile,
    task: Task,
    sandbox: SandboxManager,
    container: Container,
) -> AgentResult:
    """Protocol 模式：调用 Python Agent 类。"""
    # 动态加载 Agent 类
    if not profile.agent_class:
        return AgentResult(
            task_id=task.task_id,
            exit_code=-1,
            stderr="未指定 agent_class",
        )

    try:
        agent = _load_agent_class(profile)
    except Exception as exc:
        return AgentResult(
            task_id=task.task_id,
            exit_code=-1,
            stderr=f"加载 Agent 类失败: {exc}",
        )

    # 绑定容器到 sandbox
    sandbox.set_active_container(container)

    # 执行
    try:
        transcript = agent.run(task, sandbox)
    except Exception as exc:
        return AgentResult(
            task_id=task.task_id,
            exit_code=-1,
            stderr=f"Agent 执行失败: {exc}",
        )

    # 收集输出文件（在清除绑定前）
    output_files = _collect_output_files(sandbox, container, "/workspace")
    sandbox.clear_active_container()

    return AgentResult(
        task_id=task.task_id,
        exit_code=0,
        transcript=transcript,
        token_usage={
            "input": transcript.agent_config.get("input_tokens", 0),
            "output": transcript.agent_config.get("output_tokens", 0),
            "cache": transcript.agent_config.get("cache_tokens", 0),
        },
        cost_usd=transcript.agent_config.get("cost_usd", 0.0),
        duration=transcript.total_duration,
        output_files=output_files,
    )


def _load_agent_class(profile: AgentProfile) -> Any:
    """动态加载 Agent 类。"""
    import importlib

    if not profile.agent_class:
        raise ValueError("未指定 agent_class")

    parts = profile.agent_class.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError(f"agent_class 格式应为 'module.ClassName'，实际: {profile.agent_class}")

    module_path, class_name = parts
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    # 构造实例
    kwargs: dict[str, Any] = {}
    if profile.model:
        kwargs["model"] = profile.model
    if profile.system_prompt:
        kwargs["system_prompt"] = profile.system_prompt
    if profile.max_iterations:
        kwargs["max_iterations"] = profile.max_iterations

    return cls(**kwargs)


# ======================================================================
# Mock 适配器
# ======================================================================


def _run_mock_agent(
    profile: AgentProfile,
    task: Task,
    sandbox: SandboxManager,
    container: Container,
) -> AgentResult:
    """Mock 模式：不调用 LLM，返回模拟结果。"""
    from codepulse.env.mock_agent import MockAgent

    sandbox.set_active_container(container)
    try:
        agent = MockAgent(name=profile.name, model=profile.model or "mock")
        transcript = agent.run(task, sandbox)
    finally:
        sandbox.clear_active_container()

    return AgentResult(
        task_id=task.task_id,
        exit_code=0,
        transcript=transcript,
        duration=transcript.total_duration,
    )


# ======================================================================
# 批量试运行 — 供 CLI 和 benchmark 共用
# ======================================================================


def run_adapter_trials(
    profile: AgentProfile,
    task: Task,
    sandbox: SandboxManager,
    harness: Any,  # EvaluationHarness (避免循环导入)
    n_trials: int,
    sandbox_image: str = "codepulse-eval",
) -> list[Any]:
    """使用适配器模式执行多次 trial。

    每次 trial 创建独立容器，执行 Agent，运行验证，评分，销毁容器。

    Args:
        profile: Agent 配置。
        task: 评测任务。
        sandbox: 沙箱管理器。
        harness: EvaluationHarness 实例。
        n_trials: 试运行次数。
        sandbox_image: 沙箱镜像。

    Returns:
        Trial 对象列表。
    """

    from codepulse.data.models import AgentConfig, Trial, TrialMetrics

    agent_config = AgentConfig(
        name=profile.name,
        model=profile.model or "unknown",
    )
    trials: list[Any] = []

    for i in range(n_trials):
        trial_id = f"{task.task_id}-trial-{i}"
        container = None

        try:
            container = sandbox.create(sandbox_image)
            sandbox.set_active_container(container)

            # 注入任务文件
            _inject_task_files(task, sandbox, container)

            # 执行 Agent
            result = run_agent(profile, task, sandbox, container)

            # 构建 Trial
            trial = Trial(
                trial_id=trial_id,
                task_id=task.task_id,
                agent_config=agent_config,
                outcome={
                    "exit_code": result.exit_code,
                    "stdout": result.stdout[:4096],
                    "stderr": result.stderr[:4096],
                    "total_duration": result.duration,
                    "total_tokens": result.token_usage.get("input", 0)
                    + result.token_usage.get("output", 0),
                    "transcript_events": len(result.transcript.events)
                    if result.transcript
                    else 0,
                    "tool_call_count": result.transcript.tool_call_count
                    if result.transcript
                    else 0,
                },
                metrics=TrialMetrics(
                    total_tokens=result.token_usage.get("input", 0)
                    + result.token_usage.get("output", 0),
                    input_tokens=result.token_usage.get("input", 0),
                    output_tokens=result.token_usage.get("output", 0),
                    total_duration=result.duration,
                    cost_usd=result.cost_usd,
                ),
            )

            # 运行验证（pytest）
            _run_verification(task, sandbox, container, trial)

            # 评分
            dimension_scores = harness.grade(task, trial)
            total_score = harness.compute_total_score(dimension_scores)
            trial.scores = {dim.value: score for dim, score in dimension_scores.items()}
            trial.success = _is_success(dimension_scores, total_score)

        except Exception:
            logger.exception("Trial %s 执行失败", trial_id)
            trial = Trial(
                trial_id=trial_id,
                task_id=task.task_id,
                agent_config=agent_config,
                outcome={"error": "execution failed"},
            )
        finally:
            sandbox.clear_active_container()
            if container:
                try:
                    sandbox.destroy(container)
                except Exception:
                    logger.warning("销毁容器失败: %s", getattr(container, "id", "unknown")[:12])

        trials.append(trial)

    return trials


def _is_success(
    dimension_scores: dict[ScoreDimension, float], total_score: float
) -> bool:
    """Use official-test success when functional is the only active grader."""
    if set(dimension_scores) == {ScoreDimension.FUNCTIONAL}:
        return dimension_scores[ScoreDimension.FUNCTIONAL] >= 1.0
    return total_score >= PASS_THRESHOLD


def _inject_task_files(
    task: Any, sandbox: SandboxManager, container: Any
) -> None:
    """注入任务文件到容器。"""
    from codepulse.env.sandbox_utils import SandboxUtils

    utils = SandboxUtils(sandbox)
    sandbox.execute(container, "mkdir -p /workspace")

    # 注入 task.json
    task_json = _build_task_json(task)
    utils.write_file(container, "task.json", task_json)

    # 注入输入代码
    input_code = task.input.get("input_code", "")
    if input_code:
        utils.write_file(container, "input.py", input_code)
        utils.write_file(container, "solution.py", input_code)


def _run_verification(
    task: Any, sandbox: SandboxManager, container: Any, trial: Any
) -> None:
    """在容器中运行验证测试（pytest）。"""
    from codepulse.env.sandbox_utils import SandboxUtils

    test_cases = task.ground_truth.get("test_cases", [])
    if not test_cases:
        return

    # 构建测试代码
    if task.language.lower() not in ("python", "py"):
        return

    lines = ["# Auto-generated test file", ""]
    lines.append("import sys")
    lines.append('sys.path.insert(0, "/workspace")')
    lines.append("")
    # Import agent's solution
    lines.append("try:")
    lines.append("    from solution import *")
    lines.append("except ImportError:")
    lines.append("    pass")
    lines.append("")
    for i, tc in enumerate(test_cases):
        lines.append(f"def test_case_{i+1}():")
        for sub_line in tc.strip().split("\n"):
            lines.append(f"    {sub_line}")
        lines.append("")
    test_code = "\n".join(lines)

    utils = SandboxUtils(sandbox)
    try:
        utils.write_file(container, "test_solution.py", test_code)
        result = sandbox.execute(
            container,
            "cd /workspace && python -m pytest test_solution.py -v "
            "--tb=short 2>&1",
        )

        # Parse pytest output for pass/fail counts
        stdout = result.stdout or ""
        import re as _re
        summary_line = ""
        for line in stdout.split("\n"):
            if "passed" in line and "failed" in line:
                summary_line = line
                break
        if summary_line:
            passed_m = _re.search(r"(\d+)\s+passed", summary_line)
            failed_m = _re.search(r"(\d+)\s+failed", summary_line)
            if passed_m:
                trial.outcome["pytest_passed"] = int(passed_m.group(1))
            if failed_m:
                trial.outcome["pytest_failed"] = int(failed_m.group(1))
            trial.outcome["pytest_total"] = int(passed_m.group(1)) + int(failed_m.group(1)) if passed_m and failed_m else 0
        trial.outcome["exit_code"] = result.exit_code
        trial.outcome["stdout"] = (result.stdout or "")[:4096]
        trial.outcome["stderr"] = (result.stderr or "")[:4096]
    except Exception:
        logger.warning("验证执行失败: task=%s", task.task_id if task else "unknown")
