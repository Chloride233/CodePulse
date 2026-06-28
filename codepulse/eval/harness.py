"""评测编排器 — 协调评测流程。

编排 Agent 执行、沙箱验证、Grader 评分、结果收集、分数聚合。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codepulse.data.models import Task
    from codepulse.data.protocols import Agent, Grader
    from codepulse.env.sandbox import SandboxManager

from codepulse.data.models import AgentConfig, Trial, TrialMetrics
from codepulse.eval.scoring import PASS_THRESHOLD, ScoreDimension, aggregate_scores

logger = logging.getLogger(__name__)

# 默认沙箱镜像
_DEFAULT_IMAGE = "codepulse-eval"


class EvaluationHarness:
    """评测编排器。

    协调 Agent 执行 → 沙箱验证 → Grader 评分 → 分数聚合。
    支持注入真实 Agent 或 MockAgent，通过 Agent Protocol 实现多模型切换。

    Attributes:
        sandbox: Docker 沙箱管理器。
        graders: Grader 列表，每个 Grader 负责一个评分维度。
        sandbox_image: 沙箱 Docker 镜像。
    """

    def __init__(
        self,
        sandbox: SandboxManager | None = None,
        graders: list[Grader] | None = None,
        sandbox_image: str = _DEFAULT_IMAGE,
    ) -> None:
        """初始化评测编排器。

        Args:
            sandbox: Docker 沙箱管理器。为 None 时跳过容器相关操作
                （仅适用于 mock agent，不执行 pytest/lint 验证）。
            graders: Grader 列表，默认使用空列表。
            sandbox_image: 沙箱 Docker 镜像。
        """
        self.sandbox = sandbox
        self.graders: list[Grader] = graders if graders is not None else []
        self.sandbox_image = sandbox_image

    def run_task(
        self,
        task: Task,
        agent: Agent,
        n_trials: int = 5,
        max_workers: int = 4,
    ) -> list[Trial]:
        """运行一个任务的多次试运行，支持并发。

        当 sandbox 可用且 max_workers > 1 时使用 ThreadPoolExecutor 并行执行。
        不支持 Docker 时自动回退到串行执行。
        """
        from codepulse.env.sandbox_utils import SandboxUtils

        agent_config = AgentConfig(name=agent.name, model=agent.model)

        # Sequential path (always works, including mock agent)
        if self.sandbox is None or max_workers <= 1:
            return self._run_trials_sequential(task, agent, agent_config, n_trials)

        # Parallel path (requires Docker sandbox)
        import concurrent.futures

        def _run_one(idx: int) -> Trial:
            trial_id = f"{task.task_id}-trial-{idx}"
            container = None
            try:
                assert self.sandbox is not None
                container = self.sandbox.create(self.sandbox_image)
                utils = SandboxUtils(self.sandbox)
                task_files = self._extract_task_files(task)
                if task_files:
                    utils.setup_workspace(container, task_files)
                self._bind_active_container(container)
                transcript = agent.run(task, self.sandbox)
                exec_result = self._run_sandbox_checks(task, utils, container)
                self.sandbox.clear_active_container()
                trial = self._build_trial(trial_id, task.task_id, agent_config, transcript, exec_result)
                dimension_scores = self.grade(task, trial)
                total_score = self.compute_total_score(dimension_scores)
                trial.scores = {dim.value: score for dim, score in dimension_scores.items()}
                trial.success = total_score >= PASS_THRESHOLD
                return trial
            except Exception:
                logger.exception("Trial %s failed", trial_id)
                return Trial(trial_id, task.task_id, agent_config, outcome={"error": "execution failed"})
            finally:
                if container is not None and self.sandbox is not None:
                    try:
                        self.sandbox.destroy(container)
                    except Exception:
                        logger.warning("Container destroy failed")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            return list(pool.map(_run_one, range(n_trials)))

    def _run_trials_sequential(
        self, task: Task, agent: Agent, agent_config: AgentConfig, n_trials: int,
    ) -> list[Trial]:
        """串行执行多次试运行（mock agent 兼容）。"""
        from codepulse.env.sandbox_utils import SandboxUtils

        trials: list[Trial] = []

        for i in range(n_trials):
            trial_id = f"{task.task_id}-trial-{i}"
            container = None

            try:
                # Mock agent path: no sandbox, skip container ops
                if self.sandbox is None:
                    transcript = agent.run(task, None)  # type: ignore[arg-type]
                    trial = self._build_trial(
                        trial_id=trial_id,
                        task_id=task.task_id,
                        agent_config=agent_config,
                        transcript=transcript,
                        exec_result={"exit_code": 0, "stdout": "", "stderr": ""},
                    )
                else:
                    container = self.sandbox.create(self.sandbox_image)
                    utils = SandboxUtils(self.sandbox)

                    # 写入任务文件（如有）
                    task_files = self._extract_task_files(task)
                    if task_files:
                        utils.setup_workspace(container, task_files)

                    # 设置 sandbox 的活跃容器引用（工具需要）
                    self._bind_active_container(container)

                    # 使用 Agent 执行任务
                    transcript = agent.run(task, self.sandbox)

                    # 运行沙箱级验证（pytest、静态分析等）
                    exec_result = self._run_sandbox_checks(task, utils, container)

                    # 清除活跃容器绑定
                    self.sandbox.clear_active_container()

                    # 构建 Trial
                    trial = self._build_trial(
                        trial_id=trial_id,
                        task_id=task.task_id,
                        agent_config=agent_config,
                        transcript=transcript,
                        exec_result=exec_result,
                    )

            except Exception:
                logger.exception("试运行 %s 执行失败", trial_id)
                trial = Trial(
                    trial_id=trial_id,
                    task_id=task.task_id,
                    agent_config=agent_config,
                    outcome={"error": "execution failed"},
                )
            finally:
                if container is not None and self.sandbox is not None:
                    try:
                        self.sandbox.destroy(container)
                    except Exception:
                        logger.warning("销毁容器失败: %s", container.id[:12])

            # 评分
            dimension_scores = self.grade(task, trial)
            total_score = self.compute_total_score(dimension_scores)
            trial.scores = {dim.value: score for dim, score in dimension_scores.items()}
            trial.success = total_score >= PASS_THRESHOLD

            logger.debug(
                "试运行 %s: 总分=%.2f, 成功=%s",
                trial_id,
                total_score,
                trial.success,
            )
            trials.append(trial)

        return trials

    def grade(self, task: Task, trial: Trial) -> dict[ScoreDimension, float]:
        """对一次试运行进行多维度评分。

        Args:
            task: 评测任务。
            trial: 试运行记录。

        Returns:
            各维度得分（0-1 之间的比例）。
        """
        dimension_scores: dict[ScoreDimension, float] = {}

        for grader in self.graders:
            try:
                result = grader.grade(task, trial)
                dimension_scores[result.dimension] = result.score
            except Exception:
                logger.exception(
                    "Grader '%s' 评分失败，跳过该维度",
                    grader.name,
                )

        return dimension_scores

    def compute_total_score(self, dimension_scores: dict[ScoreDimension, float]) -> float:
        """聚合各维度分数为总分。

        Args:
            dimension_scores: 各维度得分。

        Returns:
            总分（0-100）。
        """
        return aggregate_scores(dimension_scores)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _extract_task_files(self, task: Task) -> dict[str, str]:
        """从任务定义中提取需要写入沙箱的文件。

        Args:
            task: 评测任务。

        Returns:
            文件路径到内容的映射。
        """
        files: dict[str, str] = {}

        input_code = task.input.get("input_code", "")
        if input_code:
            # 根据语言确定文件名
            lang = task.language.lower()
            if lang in ("python", "py"):
                files["solution.py"] = input_code
            elif lang in ("javascript", "js", "typescript", "ts"):
                files["solution.js"] = input_code
            elif lang in ("rust",):
                files["src/main.rs"] = input_code
            elif lang in ("go",):
                files["main.go"] = input_code
            else:
                files["solution.txt"] = input_code

        # 写入测试文件（如有）
        test_cases = task.ground_truth.get("test_cases", [])
        if test_cases and task.language.lower() in ("python", "py"):
            test_code = self._build_test_code(task, test_cases)
            if test_code:
                files["test_solution.py"] = test_code

        # 写入反向测试（negative test cases）
        negative_cases = task.ground_truth.get("negative_test_cases", [])
        if negative_cases and task.language.lower() in ("python", "py"):
            neg_code = self._build_negative_test_code(task, negative_cases)
            if neg_code:
                files["test_negative.py"] = neg_code

        return files

    def _build_test_code(self, task: Task, test_cases: list[str]) -> str:
        """从 test_cases 构建 pytest 测试文件。

        Args:
            task: 评测任务。
            test_cases: 测试命令列表。

        Returns:
            pytest 测试代码。
        """
        lines = ['"""自动生成的测试文件。"""', ""]
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
            if tc.startswith("python ") or tc.startswith("pytest "):
                # 跳过命令形式的 test case
                continue
            # 假设是 assert 语句或可执行的 Python 代码
            lines.append(f"def test_case_{i+1}():")
            for sub_line in tc.strip().split("\n"):
                lines.append(f"    {sub_line}")
            lines.append("")

        return "\n".join(lines)

    def _build_negative_test_code(self, task: Task, negative_cases: list[str]) -> str:
        """从 negative_test_cases 构建反向测试文件。

        反向测试验证 Agent 的解决方案不会错误地通过不应通过的场景。
        如果任何反向测试 PASS，说明存在 false positive。
        """
        lines = ['"""自动生成的反向测试文件 — 测试"不应通过"的场景。"""', ""]

        for i, tc in enumerate(negative_cases):
            lines.append(f"def negative_test_{i+1}():")
            for sub_line in tc.strip().split("\n"):
                lines.append(f"    {sub_line}")
            lines.append("")

        return "\n".join(lines)

    def _bind_active_container(self, container: Any) -> Any:
        """将容器绑定到 sandbox，供工具系统访问。

        通过 SandboxManager.set_active_container() 公开 API 绑定。

        Args:
            container: 容器句柄。

        Returns:
            同一个容器句柄。
        """
        assert self.sandbox is not None
        self.sandbox.set_active_container(container)
        return container

    def _run_sandbox_checks(
        self,
        task: Task,
        utils: Any,
        container: Any,
    ) -> dict[str, Any]:
        """运行沙箱级验证检查。

        Args:
            task: 评测任务。
            utils: SandboxUtils 实例。
            container: 容器句柄。

        Returns:
            检查结果字典。
        """
        result: dict[str, Any] = {
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "pytest_total": 0,
            "pytest_passed": 0,
            "ruff_violations": 0,
            "mypy_errors": 0,
        }

        assert self.sandbox is not None

        test_cases = task.ground_truth.get("test_cases", [])
        if not test_cases:
            result["exit_code"] = 0
            return result

        # 运行 pytest
        try:
            pytest_result = utils.run_pytest(container)
            result["exit_code"] = pytest_result.exit_code
            result["stdout"] = pytest_result.stdout
            result["stderr"] = pytest_result.stderr
            result["pytest_total"] = pytest_result.total
            result["pytest_passed"] = pytest_result.passed
        except Exception:
            logger.exception("pytest 执行失败")

        # 运行 ruff（Python 项目）
        if task.language.lower() in ("python", "py"):
            try:
                ruff_result = self.sandbox.execute(container, "cd /workspace && ruff check . --output-format=json 2>/dev/null || true")
                if ruff_result.stdout.strip():
                    import json as _json
                    ruff_output = _json.loads(ruff_result.stdout)
                    result["ruff_violations"] = len(ruff_output) if isinstance(ruff_output, list) else 0
            except Exception:
                logger.warning("ruff check 执行失败")

        # 运行反向测试（test_negative.py）
        negative_cases = task.ground_truth.get("negative_test_cases", [])
        if negative_cases and task.language.lower() in ("python", "py"):
            try:
                neg_result = self.sandbox.execute(
                    container,
                    "cd /workspace && python -m pytest test_negative.py -v --tb=short 2>&1 || true",
                )
                # 反向测试"通过"意味着 Agent 错误地通过了不应通过的场景
                # exit_code == 0: 至少一个反向测试失败（期望行为）
                # exit_code != 0: 所有反向测试都通过（异常行为，false positive）
                has_false_positive = (
                    neg_result.exit_code is not None
                    and neg_result.exit_code == 0
                )
                result["negative_test_failures"] = 0 if has_false_positive else 1
                result["negative_stdout"] = (neg_result.stdout or "")[:2048]
            except Exception:
                logger.warning("反向测试执行失败")

        return result

    def _build_trial(
        self,
        trial_id: str,
        task_id: str,
        agent_config: AgentConfig,
        transcript: Any,
        exec_result: dict[str, Any],
    ) -> Trial:
        """从 Transcript 和执行结果构建 Trial。

        Args:
            trial_id: 试运行 ID。
            task_id: 任务 ID。
            agent_config: Agent 配置。
            transcript: Agent 执行轨迹。
            exec_result: 沙箱验证结果。

        Returns:
            Trial 对象。
        """
        # 从 transcript 提取指标
        metrics = TrialMetrics(
            total_tokens=transcript.total_tokens,
            input_tokens=transcript.agent_config.get("input_tokens", 0),
            output_tokens=transcript.agent_config.get("output_tokens", 0),
            cache_tokens=transcript.agent_config.get("cache_tokens", 0),
            total_duration=transcript.total_duration,
            tool_call_count=transcript.tool_call_count,
            cost_usd=transcript.agent_config.get("cost_usd", 0.0),
        )

        # 合并 transcript 事件统计和执行结果到 outcome
        outcome: dict[str, Any] = {
            "transcript_events": len(transcript.events),
            "total_tokens": transcript.total_tokens,
            "total_duration": transcript.total_duration,
            "tool_call_count": transcript.tool_call_count,
            # 沙箱验证结果
            "exit_code": exec_result.get("exit_code", -1),
            "stdout": exec_result.get("stdout", ""),
            "stderr": exec_result.get("stderr", ""),
            "pytest_total": exec_result.get("pytest_total", 0),
            "pytest_passed": exec_result.get("pytest_passed", 0),
            "ruff_violations": exec_result.get("ruff_violations", 0),
            "mypy_errors": exec_result.get("mypy_errors", 0),
        }

        return Trial(
            trial_id=trial_id,
            task_id=task_id,
            agent_config=agent_config,
            outcome=outcome,
            metrics=metrics,
        )
