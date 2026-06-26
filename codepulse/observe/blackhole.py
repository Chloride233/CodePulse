"""黑洞模式检测。

三个 Token 黑洞：
- 循环试错：Write+Bash(test) 反复出现
- 上下文膨胀：input_tokens 阶梯式增长
- 过度谨慎：LLM span 占比 > 80%
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from codepulse.observe.trace import EventType, Transcript


@dataclass(frozen=True)
class BlackholeDetection:
    """黑洞检测结果。"""

    blackhole_type: str
    details: dict[str, Any]


class BlackholeDetector:
    """黑洞模式检测器。"""

    # 循环试错阈值
    LOOP_THRESHOLD = 3
    # 上下文膨胀增长率阈值
    BLOAT_GROWTH_THRESHOLD = 2.0
    # 过度谨慎 LLM 时间占比阈值
    OVER_CAUTION_RATIO = 0.8

    def detect(self, trace: Transcript) -> list[BlackholeDetection]:
        """检测所有黑洞模式。

        Args:
            trace: Agent 执行轨迹。

        Returns:
            检测到的黑洞列表。
        """
        detections: list[BlackholeDetection] = []

        loop = self.detect_loop_trial(trace)
        if loop:
            detections.append(loop)

        bloat = self.detect_context_bloat(trace)
        if bloat:
            detections.append(bloat)

        caution = self.detect_over_caution(trace)
        if caution:
            detections.append(caution)

        return detections

    def detect_loop_trial(self, trace: Transcript) -> BlackholeDetection | None:
        """检测循环试错。

        特征：Write+Bash(test) 反复出现 >= LOOP_THRESHOLD 次。

        Args:
            trace: Agent 执行轨迹。

        Returns:
            检测结果，无则返回 None。
        """
        tool_calls = [
            e for e in trace.events
            if e.event_type == EventType.TOOL_CALL
        ]

        # 简化检测：连续的 write+test 模式
        write_test_count = 0
        for i, event in enumerate(tool_calls):
            tool_name = event.content.get("tool", "")
            if tool_name in ("Write", "Edit"):
                # 检查后续是否有 test 执行
                for j in range(i + 1, min(i + 3, len(tool_calls))):
                    next_tool = tool_calls[j].content.get("tool", "")
                    if next_tool == "Bash" and "test" in tool_calls[j].content.get("command", ""):
                        write_test_count += 1
                        break

        if write_test_count >= self.LOOP_THRESHOLD:
            return BlackholeDetection(
                blackhole_type="loop_trial",
                details={"write_test_pairs": write_test_count},
            )
        return None

    def detect_context_bloat(self, trace: Transcript) -> BlackholeDetection | None:
        """检测上下文膨胀。

        特征：input_tokens 增长率 > BLOAT_GROWTH_THRESHOLD。

        Args:
            trace: Agent 执行轨迹。

        Returns:
            检测结果，无则返回 None。
        """
        input_tokens = [
            e.token_usage.get("input", 0)
            for e in trace.events
            if e.event_type == EventType.LLM_CALL and e.token_usage.get("input", 0) > 0
        ]

        if len(input_tokens) < 5:
            return None

        growth_rate = (input_tokens[-1] - input_tokens[0]) / max(input_tokens[0], 1)
        if growth_rate > self.BLOAT_GROWTH_THRESHOLD:
            return BlackholeDetection(
                blackhole_type="context_bloat",
                details={"growth_rate": round(growth_rate, 2)},
            )
        return None

    def detect_over_caution(self, trace: Transcript) -> BlackholeDetection | None:
        """检测过度谨慎。

        特征：LLM 调用时间占比 > OVER_CAUTION_RATIO。

        Args:
            trace: Agent 执行轨迹。

        Returns:
            检测结果，无则返回 None。
        """
        if trace.total_duration <= 0:
            return None

        llm_time = sum(
            e.duration for e in trace.events if e.event_type == EventType.LLM_CALL
        )
        llm_ratio = llm_time / trace.total_duration

        if llm_ratio > self.OVER_CAUTION_RATIO:
            return BlackholeDetection(
                blackhole_type="over_caution",
                details={"llm_ratio": round(llm_ratio, 2)},
            )
        return None
