"""Command-line workflow for Phase 2 LLM-as-Judge calibration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from codepulse.eval.calibration_analysis import (
    analyze_calibration_study,
    render_calibration_report,
)
from codepulse.eval.calibration_review import (
    load_jsonl,
    prepare_review_files,
    run_functional_judge,
    validate_judge_observations,
    validate_review_packets,
    validate_review_responses,
    write_jsonl,
)
from codepulse.eval.calibration_review_server import run_review_server


def main() -> None:
    """Run deterministic preparation/validation or the explicit live Judge step."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--input", required=True)
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--seed", type=int, default=20260713)
    prepare.add_argument("--reviewer-1", required=True)
    prepare.add_argument("--reviewer-2", required=True)
    prepare.add_argument("--force", action="store_true")

    validate = subparsers.add_parser("validate")
    validate.add_argument("--packets", required=True)
    validate.add_argument("--responses", required=True)

    review = subparsers.add_parser("review")
    review.add_argument("--packets", required=True)
    review.add_argument("--responses", required=True)

    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--packets-1", required=True)
    analyze.add_argument("--mapping-1", required=True)
    analyze.add_argument("--responses-1", required=True)
    analyze.add_argument("--packets-2", required=True)
    analyze.add_argument("--mapping-2", required=True)
    analyze.add_argument("--responses-2", required=True)
    analyze.add_argument("--judge-observations", required=True)
    analyze.add_argument("--adjudications")
    analyze.add_argument("--score-rows")
    analyze.add_argument("--position-pairs")
    analyze.add_argument("--length-pairs")
    analyze.add_argument("--self-preference-rows")
    analyze.add_argument("--output-json", required=True)
    analyze.add_argument("--output-report", required=True)
    analyze.add_argument("--force", action="store_true")

    judge = subparsers.add_parser("judge")
    judge.add_argument("--packets", required=True)
    judge.add_argument("--output", required=True)
    judge.add_argument("--model", required=True)
    judge.add_argument("--force", action="store_true")

    args = parser.parse_args()
    if args.command == "prepare":
        manifest = prepare_review_files(
            args.input,
            args.output_dir,
            seed=args.seed,
            reviewer_1=args.reviewer_1,
            reviewer_2=args.reviewer_2,
            force=args.force,
        )
        print(json.dumps(manifest, ensure_ascii=False))
        return

    if args.command == "validate":
        packets = load_jsonl(Path(args.packets))
        responses = load_jsonl(Path(args.responses))
        errors = validate_review_responses(packets, responses)
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False))
        if errors:
            raise SystemExit(1)
        return

    if args.command == "review":
        run_review_server(args.packets, args.responses)
        return

    if args.command == "analyze":
        _run_analysis(args)
        return

    packets = load_jsonl(Path(args.packets))
    output = Path(args.output)
    if output.exists() and not args.force:
        raise FileExistsError(f"refusing to overwrite existing artifact: {output}")
    packet_errors = validate_review_packets(packets)
    if packet_errors:
        raise ValueError("invalid review packets: " + "; ".join(packet_errors))
    observations = run_functional_judge(packets, model=args.model)
    observation_errors = validate_judge_observations(packets, observations)
    if observation_errors:
        raise ValueError("invalid Judge observations: " + "; ".join(observation_errors))
    output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(output, observations)
    print(json.dumps({"observations": len(observations)}, ensure_ascii=False))


def _run_analysis(args: argparse.Namespace) -> None:
    output_json = Path(args.output_json)
    output_report = Path(args.output_report)
    existing = [path for path in (output_json, output_report) if path.exists()]
    if existing and not args.force:
        raise FileExistsError(f"refusing to overwrite existing artifact: {existing[0]}")
    analysis = analyze_calibration_study(
        packets_1=load_jsonl(Path(args.packets_1)),
        mapping_1=load_jsonl(Path(args.mapping_1)),
        responses_1=load_jsonl(Path(args.responses_1)),
        packets_2=load_jsonl(Path(args.packets_2)),
        mapping_2=load_jsonl(Path(args.mapping_2)),
        responses_2=load_jsonl(Path(args.responses_2)),
        judge_observations=load_jsonl(Path(args.judge_observations)),
        adjudications=_optional_jsonl(args.adjudications),
        score_rows=_optional_jsonl(args.score_rows),
        position_pairs=_optional_jsonl(args.position_pairs),
        length_pairs=_optional_jsonl(args.length_pairs),
        self_preference_rows=_optional_jsonl(args.self_preference_rows),
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_report.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output_report.write_text(render_calibration_report(analysis), encoding="utf-8")
    print(json.dumps({"status": analysis["status"]}, ensure_ascii=False))


def _optional_jsonl(path: str | None) -> list[dict[str, Any]] | None:
    return load_jsonl(Path(path)) if path else None


if __name__ == "__main__":
    main()
