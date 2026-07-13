"""Deterministic stratified sampling from benchmark Trial JSONL."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def stratified_sample(
    rows: list[dict[str, Any]], sample_size: int, seed: int
) -> list[dict[str, Any]]:
    """Balance Agents, cover tasks, and always retain observed failures."""
    if sample_size <= 0 or sample_size > len(rows):
        raise ValueError("sample_size must be between 1 and the row count")
    agents = sorted({row["agent_name"] for row in rows})
    if sample_size % len(agents) != 0:
        raise ValueError("sample_size must divide evenly across Agents")

    quota = sample_size // len(agents)
    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()

    for agent in agents:
        agent_rows = [row for row in rows if row["agent_name"] == agent]
        failures = [row for row in agent_rows if not row["success"]]
        if len(failures) > quota:
            raise ValueError(f"Agent {agent} has more failures than its quota")
        selected.extend(failures)
        selected_ids.update(row["trial_id"] for row in failures)

        by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in agent_rows:
            if row["trial_id"] not in selected_ids:
                by_task[row["task_id"]].append(row)
        for candidates in by_task.values():
            rng.shuffle(candidates)

        needed = quota - len(failures)
        while needed:
            task_ids = sorted(task_id for task_id, values in by_task.items() if values)
            if not task_ids:
                raise ValueError(f"Not enough rows for Agent {agent}")
            rng.shuffle(task_ids)
            for task_id in task_ids:
                if needed == 0:
                    break
                row = by_task[task_id].pop()
                selected.append(row)
                selected_ids.add(row["trial_id"])
                needed -= 1

    selected.sort(key=lambda row: (row["task_id"], row["repetition"], row["agent_name"]))
    return selected


def build_annotation_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create honest annotation templates without inventing review scores."""
    records = []
    for index, row in enumerate(rows, start=1):
        records.append(
            {
                "sample_id": f"cal-v1-{index:03d}",
                "source_trial_id": row["trial_id"],
                "task_id": row["task_id"],
                "agent_name": row["agent_name"],
                "repetition": row["repetition"],
                "stratum": "success" if row["success"] else "failure",
                "deterministic_evidence": {
                    "success": row["success"],
                    "scores": row["scores"],
                    "outcome": row["outcome"],
                    "metrics": row["metrics"],
                },
                "artifact_status": "missing_final_code_and_full_transcript",
                "eligible_dimensions": ["functional_evidence"],
                "ineligible_dimensions": ["process_quality", "experience_alignment"],
                "llm_judge": {"model": None, "score": None, "reasoning": None},
                "human_review_round_1": {
                    "reviewer_id": None,
                    "score": None,
                    "label": None,
                    "note": None,
                },
                "human_review_round_2": {
                    "reviewer_id": None,
                    "score": None,
                    "label": None,
                    "note": None,
                },
            }
        )
    return records


def write_sample(
    input_path: str | Path, output_path: str | Path, sample_size: int, seed: int
) -> dict[str, Any]:
    """Sample Trial JSONL and write annotation JSONL plus a manifest."""
    source = Path(input_path)
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    sampled = stratified_sample(rows, sample_size, seed)
    records = build_annotation_records(sampled)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "source": str(source),
        "output": str(output),
        "seed": seed,
        "sample_size": len(records),
        "agents": dict(Counter(record["agent_name"] for record in records)),
        "tasks": len({record["task_id"] for record in records}),
        "strata": dict(Counter(record["stratum"] for record in records)),
        "annotation_status": "not_started",
        "artifact_limitation": "Phase 1 did not persist final code or full transcripts",
    }
    output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260713)
    args = parser.parse_args()
    print(
        json.dumps(
            write_sample(args.input, args.output, args.sample_size, args.seed),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
