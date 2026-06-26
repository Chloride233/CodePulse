"""黑洞模式检测测试。"""

from codepulse.observe.blackhole import BlackholeDetector
from codepulse.observe.trace import EventType, TraceEvent, Transcript


class TestBlackholeDetector:
    """BlackholeDetector 测试。"""

    def setup_method(self) -> None:
        self.detector = BlackholeDetector()

    def _make_event(
        self,
        event_type: EventType,
        content: dict | None = None,
        token_usage: dict | None = None,
        duration: float = 0.0,
    ) -> TraceEvent:
        return TraceEvent(
            timestamp=0.0,
            event_type=event_type,
            content=content or {},
            token_usage=token_usage or {},
            duration=duration,
        )

    def test_no_blackhole(self) -> None:
        """正常轨迹无黑洞。"""
        trace = Transcript(session_id="test")
        trace.add_event(self._make_event(EventType.LLM_CALL, duration=1.0))
        trace.add_event(self._make_event(EventType.TOOL_CALL, content={"tool": "Read"}, duration=0.5))
        assert self.detector.detect(trace) == []

    def test_context_bloat(self) -> None:
        """上下文膨胀检测。"""
        trace = Transcript(session_id="test")
        # 模拟 input tokens 快速增长
        tokens = [100, 150, 200, 300, 500, 1000, 2000]
        for t in tokens:
            trace.add_event(self._make_event(
                EventType.LLM_CALL,
                token_usage={"input": t, "output": 50},
                duration=1.0,
            ))
        detections = self.detector.detect(trace)
        assert any(d.blackhole_type == "context_bloat" for d in detections)

    def test_over_caution(self) -> None:
        """过度谨慎检测。"""
        trace = Transcript(session_id="test")
        # LLM 调用占 90% 时间 (9s LLM + 1s tool = 10s total, 90%)
        trace.add_event(self._make_event(EventType.LLM_CALL, duration=4.0))
        trace.add_event(self._make_event(EventType.LLM_CALL, duration=5.0))
        trace.add_event(self._make_event(EventType.TOOL_CALL, duration=1.0))
        detections = self.detector.detect(trace)
        assert any(d.blackhole_type == "over_caution" for d in detections)

    def test_loop_trial(self) -> None:
        """循环试错检测。"""
        trace = Transcript(session_id="test")
        # 模拟 Write+Bash(test) 反复出现
        for _ in range(4):
            trace.add_event(self._make_event(
                EventType.TOOL_CALL,
                content={"tool": "Write", "file_path": "test.py"},
            ))
            trace.add_event(self._make_event(
                EventType.TOOL_CALL,
                content={"tool": "Bash", "command": "pytest test.py"},
            ))
        detections = self.detector.detect(trace)
        assert any(d.blackhole_type == "loop_trial" for d in detections)
