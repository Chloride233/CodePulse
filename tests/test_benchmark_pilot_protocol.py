"""Regression checks for the locked Phase 1 benchmark pilot protocol."""

from pathlib import Path

PROTOCOL_PATH = Path(__file__).parents[1] / "docs" / "benchmark-pilot-protocol.md"


def test_benchmark_pilot_protocol_fixed_scope_and_metrics_present() -> None:
    protocol = PROTOCOL_PATH.read_text(encoding="utf-8")

    assert "协议版本：`pilot-v1`" in protocol
    assert all(f"HumanEval/{task_id}" in protocol for task_id in range(20))
    assert "计划 Trial 总数 | 120" in protocol
    assert all(metric in protocol for metric in ("pass@1", "pass@3", "pass^3", "P50/P95"))


def test_benchmark_pilot_protocol_reproducibility_and_budget_gates_present() -> None:
    protocol = PROTOCOL_PATH.read_text(encoding="utf-8")

    assert all(
        frozen_item in protocol
        for frozen_item in (
            "不可变模型版本 ID",
            "system prompt",
            "随机种子",
            "Git commit SHA",
            "任务清单 SHA-256",
            "镜像 digest",
            "lockfile SHA-256",
        )
    )
    assert "pilot 总实际成本 | USD 20.00" in protocol
    assert "codepulse benchmark preflight" in protocol
    assert "状态：**已锁定，尚未执行**" in protocol
