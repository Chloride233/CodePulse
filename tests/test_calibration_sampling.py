"""Tests for deterministic Phase 2 calibration sampling."""

from codepulse.eval.calibration_sampling import (
    build_annotation_records,
    stratified_sample,
)


def _rows() -> list[dict[str, object]]:
    rows = []
    for agent in ("a", "b"):
        for task in range(4):
            for repetition in range(3):
                rows.append(
                    {
                        "trial_id": f"t{task}-r{repetition}-{agent}",
                        "task_id": f"t{task}",
                        "agent_name": agent,
                        "repetition": repetition,
                        "success": not (agent == "a" and task == 3 and repetition == 2),
                        "scores": {},
                        "outcome": {},
                        "metrics": {},
                    }
                )
    return rows


def test_calibration_sample_balances_agents_and_retains_failure() -> None:
    sampled = stratified_sample(_rows(), 16, 42)

    assert len(sampled) == 16
    assert sum(row["agent_name"] == "a" for row in sampled) == 8
    assert sum(row["agent_name"] == "b" for row in sampled) == 8
    assert any(not row["success"] for row in sampled)
    assert {row["task_id"] for row in sampled} == {"t0", "t1", "t2", "t3"}
    assert sampled == stratified_sample(_rows(), 16, 42)


def test_calibration_annotation_fields_are_unscored() -> None:
    record = build_annotation_records(stratified_sample(_rows(), 16, 42))[0]

    assert record["llm_judge"]["score"] is None
    assert record["human_review_round_1"]["score"] is None
    assert record["human_review_round_2"]["score"] is None
    assert record["artifact_status"] == "missing_final_code_and_full_transcript"
