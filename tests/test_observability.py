"""Tests for observability tools — TraceCollector and AgentComparator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codepulse.data.models import (
    AgentConfig,
    Difficulty,
    Task,
    TaskCategory,
    TaskSource,
    Trial,
    TrialMetrics,
)
from codepulse.env.mock_agent import MockAgent
from codepulse.observe.collector import TraceCollector
from codepulse.observe.comparator import AgentComparator
from codepulse.observe.trace import EventType, TraceEvent, Transcript

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def collector(tmp_path: Path) -> TraceCollector:
    """TraceCollector 实例，输出到临时目录。"""
    return TraceCollector(output_dir=str(tmp_path))


@pytest.fixture
def sample_task() -> Task:
    """示例评测任务。"""
    return Task(
        task_id="obs-001",
        source=TaskSource.CUSTOM,
        category=TaskCategory.BUG_FIX,
        difficulty=Difficulty.EASY,
        language="python",
        input={"description": "Fix the bug"},
        ground_truth={"expected": "correct output"},
    )


@pytest.fixture
def sample_event() -> TraceEvent:
    """示例 Trace 事件。"""
    return TraceEvent(
        timestamp=1000.0,
        event_type=EventType.LLM_CALL,
        content={"prompt": "hello", "response": "world"},
        token_usage={"input": 100, "output": 50},
        duration=0.5,
    )


@pytest.fixture
def tool_event() -> TraceEvent:
    """示例 TOOL_CALL 事件。"""
    return TraceEvent(
        timestamp=1001.0,
        event_type=EventType.TOOL_CALL,
        content={"tool": "bash", "command": "ls"},
        duration=0.2,
    )


@pytest.fixture
def mock_sandbox() -> MagicMock:
    """Mock SandboxManager。"""
    return MagicMock()


# ---------------------------------------------------------------------------
# TestTraceCollector
# ---------------------------------------------------------------------------


class TestTraceCollectorStartSession:
    """TraceCollector.start_session 测试。"""

    def test_start_session_returns_transcript(self, collector: TraceCollector) -> None:
        """start_session 必须返回 Transcript 实例。"""
        transcript = collector.start_session("sess-001")
        assert isinstance(transcript, Transcript)

    def test_start_session_sets_session_id(self, collector: TraceCollector) -> None:
        """Transcript.session_id 必须等于传入的 session_id。"""
        transcript = collector.start_session("sess-abc")
        assert transcript.session_id == "sess-abc"

    def test_start_session_empty_events(self, collector: TraceCollector) -> None:
        """新建 Transcript 的事件列表应为空。"""
        transcript = collector.start_session("sess-002")
        assert transcript.events == []


class TestTraceCollectorRecordEvent:
    """TraceCollector.record_event 测试。"""

    def test_record_event_adds_to_transcript(
        self,
        collector: TraceCollector,
        sample_event: TraceEvent,
    ) -> None:
        """record_event 应将事件追加到 transcript.events。"""
        transcript = collector.start_session("sess-003")
        collector.record_event(transcript, sample_event)
        assert len(transcript.events) == 1
        assert transcript.events[0] is sample_event

    def test_record_multiple_events(
        self,
        collector: TraceCollector,
        sample_event: TraceEvent,
        tool_event: TraceEvent,
    ) -> None:
        """多次 record_event 应按顺序追加事件。"""
        transcript = collector.start_session("sess-004")
        collector.record_event(transcript, sample_event)
        collector.record_event(transcript, tool_event)
        assert len(transcript.events) == 2
        assert transcript.events[0] is sample_event
        assert transcript.events[1] is tool_event

    def test_record_event_updates_metrics(
        self,
        collector: TraceCollector,
        sample_event: TraceEvent,
    ) -> None:
        """record_event 应通过 Transcript.add_event 更新指标。"""
        transcript = collector.start_session("sess-005")
        collector.record_event(transcript, sample_event)
        assert transcript.total_tokens == 150  # 100 + 50
        assert transcript.total_duration == pytest.approx(0.5)

    def test_record_tool_call_increments_count(
        self,
        collector: TraceCollector,
        tool_event: TraceEvent,
    ) -> None:
        """记录 TOOL_CALL 事件应递增 tool_call_count。"""
        transcript = collector.start_session("sess-006")
        collector.record_event(transcript, tool_event)
        assert transcript.tool_call_count == 1


class TestTraceCollectorSaveTrace:
    """TraceCollector.save_trace 测试。"""

    def test_save_trace_creates_file(
        self,
        collector: TraceCollector,
        sample_event: TraceEvent,
    ) -> None:
        """save_trace 应创建 JSONL 文件。"""
        transcript = collector.start_session("sess-007")
        collector.record_event(transcript, sample_event)
        path = collector.save_trace(transcript, "task-1", "trial-0")
        assert path.exists()
        assert path.suffix == ".jsonl"

    def test_save_trace_file_path(
        self,
        collector: TraceCollector,
        sample_event: TraceEvent,
    ) -> None:
        """文件路径应为 output_dir / task_id / trial_id-trace.jsonl。"""
        transcript = collector.start_session("sess-008")
        collector.record_event(transcript, sample_event)
        path = collector.save_trace(transcript, "task-x", "trial-3")
        assert path == Path(collector._output_dir) / "task-x" / "trial-3-trace.jsonl"

    def test_save_trace_jsonl_line_count(
        self,
        collector: TraceCollector,
        sample_event: TraceEvent,
        tool_event: TraceEvent,
    ) -> None:
        """JSONL 文件行数应等于事件数。"""
        transcript = collector.start_session("sess-009")
        collector.record_event(transcript, sample_event)
        collector.record_event(transcript, tool_event)
        path = collector.save_trace(transcript, "task-2", "trial-1")
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_save_trace_jsonl_format(
        self,
        collector: TraceCollector,
        sample_event: TraceEvent,
    ) -> None:
        """JSONL 每行必须是合法 JSON，且包含必要字段。"""
        transcript = collector.start_session("sess-010")
        collector.record_event(transcript, sample_event)
        path = collector.save_trace(transcript, "task-3", "trial-0")
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])

        assert "timestamp" in record
        assert "event_type" in record
        assert "content" in record
        assert "token_usage" in record
        assert "duration" in record

    def test_save_trace_jsonl_field_values(
        self,
        collector: TraceCollector,
        sample_event: TraceEvent,
    ) -> None:
        """JSONL 记录字段值必须与 TraceEvent 一致。"""
        transcript = collector.start_session("sess-011")
        collector.record_event(transcript, sample_event)
        path = collector.save_trace(transcript, "task-4", "trial-0")
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])

        assert record["timestamp"] == sample_event.timestamp
        assert record["event_type"] == sample_event.event_type.value
        assert record["content"] == sample_event.content
        assert record["token_usage"] == sample_event.token_usage
        assert record["duration"] == sample_event.duration

    def test_save_trace_empty_transcript(self, collector: TraceCollector) -> None:
        """空 Transcript 应创建空文件（零行）。"""
        transcript = collector.start_session("sess-012")
        path = collector.save_trace(transcript, "task-5", "trial-0")
        content = path.read_text(encoding="utf-8")
        assert content == ""


class TestTraceCollectorWithMockAgent:
    """使用 MockAgent 集成测试 TraceCollector 完整流程。"""

    def test_full_lifecycle(
        self,
        collector: TraceCollector,
        sample_task: Task,
        mock_sandbox: MagicMock,
        tmp_path: Path,
    ) -> None:
        """完整生命周期：MockAgent.run → record → end → save。"""
        agent = MockAgent(name="test-agent", model="test-model")
        transcript = agent.run(sample_task, mock_sandbox)

        collector.start_session(transcript.session_id)
        collector.end_session(transcript)
        path = collector.save_trace(transcript, sample_task.task_id, "trial-0")

        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == len(transcript.events)

        for i, line in enumerate(lines):
            record = json.loads(line)
            assert record["event_type"] == transcript.events[i].event_type.value


# ---------------------------------------------------------------------------
# TestAgentComparator
# ---------------------------------------------------------------------------


def _make_trial(
    trial_id: str,
    task_id: str,
    agent_config: AgentConfig,
    success: bool = True,
    tokens: int = 200,
    duration: float = 1.0,
    cost: float = 0.01,
) -> Trial:
    """构造测试用 Trial。"""
    return Trial(
        trial_id=trial_id,
        task_id=task_id,
        agent_config=agent_config,
        success=success,
        metrics=TrialMetrics(
            total_tokens=tokens,
            total_duration=duration,
            tool_call_count=2,
            self_correction_count=0,
            cost_usd=cost,
        ),
    )


class TestAgentComparatorCompare:
    """AgentComparator.compare 测试。"""

    def test_compare_returns_dict(self, sample_task: Task) -> None:
        """compare 必须返回 dict。"""
        harness = MagicMock()
        agent_cfg = AgentConfig(name="agent-a", model="model-a")
        trial = _make_trial("t-0", sample_task.task_id, agent_cfg)
        harness.run_task.return_value = [trial]

        comparator = AgentComparator(harness=harness)
        results = comparator.compare(sample_task, [agent_cfg], n_trials=1)
        assert isinstance(results, dict)

    def test_compare_keys_match_agent_names(self, sample_task: Task) -> None:
        """返回 dict 的 key 应为各 Agent 的 name。"""
        harness = MagicMock()
        cfg_a = AgentConfig(name="alpha", model="m1")
        cfg_b = AgentConfig(name="beta", model="m2")

        trial_a = _make_trial("t-0", sample_task.task_id, cfg_a)
        trial_b = _make_trial("t-1", sample_task.task_id, cfg_b, success=False)
        harness.run_task.side_effect = [[trial_a], [trial_b]]

        comparator = AgentComparator(harness=harness)
        results = comparator.compare(sample_task, [cfg_a, cfg_b], n_trials=1)

        assert "alpha" in results
        assert "beta" in results
        assert len(results) == 2

    def test_compare_calls_harness_for_each_agent(self, sample_task: Task) -> None:
        """compare 应为每个 Agent 调用一次 harness.run_task。"""
        harness = MagicMock()
        cfg = AgentConfig(name="agent-x", model="mx")
        trial = _make_trial("t-0", sample_task.task_id, cfg)
        harness.run_task.return_value = [trial]

        comparator = AgentComparator(harness=harness)
        comparator.compare(sample_task, [cfg], n_trials=3)

        harness.run_task.assert_called_once_with(sample_task, cfg, n_trials=3)

    def test_compare_metrics_populated(self, sample_task: Task) -> None:
        """AgentMetrics 字段应正确聚合。"""
        harness = MagicMock()
        cfg = AgentConfig(name="agent-y", model="my")
        trials = [
            _make_trial(f"t-{i}", sample_task.task_id, cfg, success=True, tokens=100)
            for i in range(3)
        ]
        harness.run_task.return_value = trials

        comparator = AgentComparator(harness=harness)
        results = comparator.compare(sample_task, [cfg], n_trials=3)

        metrics = results["agent-y"]
        assert metrics.n_success == 3
        assert metrics.n_total == 3
        assert metrics.avg_tokens == pytest.approx(100.0)


class TestAgentComparatorGenerateReport:
    """AgentComparator.generate_report 测试。"""

    def test_generate_report_returns_string(self, sample_task: Task) -> None:
        """generate_report 必须返回字符串。"""
        harness = MagicMock()
        comparator = AgentComparator(harness=harness)

        cfg = AgentConfig(name="agent-a", model="m1")
        trial = _make_trial("t-0", sample_task.task_id, cfg)
        harness.run_task.return_value = [trial]
        results = comparator.compare(sample_task, [cfg], n_trials=1)

        report = comparator.generate_report(results)
        assert isinstance(report, str)

    def test_generate_report_contains_markdown_table(self, sample_task: Task) -> None:
        """报告应包含 Markdown 表格。"""
        harness = MagicMock()
        comparator = AgentComparator(harness=harness)

        cfg = AgentConfig(name="agent-a", model="m1")
        trial = _make_trial("t-0", sample_task.task_id, cfg)
        harness.run_task.return_value = [trial]
        results = comparator.compare(sample_task, [cfg], n_trials=1)

        report = comparator.generate_report(results)
        assert "| Agent" in report
        assert "|-------" in report
        assert "agent-a" in report

    def test_generate_report_empty_results(self) -> None:
        """空结果应返回无结果提示。"""
        harness = MagicMock()
        comparator = AgentComparator(harness=harness)
        report = comparator.generate_report({})
        assert "无结果" in report

    def test_generate_report_contains_title(self, sample_task: Task) -> None:
        """报告应以标题开头。"""
        harness = MagicMock()
        comparator = AgentComparator(harness=harness)

        cfg = AgentConfig(name="agent-b", model="m2")
        trial = _make_trial("t-0", sample_task.task_id, cfg)
        harness.run_task.return_value = [trial]
        results = comparator.compare(sample_task, [cfg], n_trials=1)

        report = comparator.generate_report(results)
        assert report.startswith("# Agent 对比报告")

    def test_generate_report_multiple_agents(self, sample_task: Task) -> None:
        """多 Agent 对比报告应包含所有 Agent 名称。"""
        harness = MagicMock()
        comparator = AgentComparator(harness=harness)

        cfg_a = AgentConfig(name="fast-agent", model="m1")
        cfg_b = AgentConfig(name="slow-agent", model="m2")
        harness.run_task.side_effect = [
            [_make_trial("t-0", sample_task.task_id, cfg_a)],
            [_make_trial("t-1", sample_task.task_id, cfg_b, success=False)],
        ]

        results = comparator.compare(sample_task, [cfg_a, cfg_b], n_trials=1)
        report = comparator.generate_report(results)

        assert "fast-agent" in report
        assert "slow-agent" in report
