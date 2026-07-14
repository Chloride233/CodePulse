"""Command-line workflow for Phase 2 LLM-as-Judge calibration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from codepulse.eval.artifacts import (
    ensure_outputs_available,
    file_sha256,
    load_jsonl,
    write_jsonl,
)
from codepulse.eval.calibration_cohort import (
    CohortNotReadyError,
    profile_diagnostic_cohort,
)
from codepulse.eval.calibration_diagnostic import (
    prepare_diagnostic_review_files,
    validate_diagnostic_responses,
)
from codepulse.eval.calibration_diagnostic_analysis import (
    analyze_diagnostic_study,
    render_diagnostic_report,
)
from codepulse.eval.calibration_diagnostic_judge import (
    run_diagnostic_judge,
    validate_diagnostic_judge_observations,
)
from codepulse.eval.calibration_diagnostic_review_server import (
    run_diagnostic_review_server,
)
from codepulse.eval.calibration_review import (
    prepare_functional_judge_files,
    run_functional_judge,
    validate_judge_observations,
    validate_review_packets,
)


def main() -> None:
    """Run deterministic preparation/validation or the explicit live Judge step."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_functional = subparsers.add_parser("prepare-functional")
    prepare_functional.add_argument("--input", required=True)
    prepare_functional.add_argument("--output-dir", required=True)
    prepare_functional.add_argument("--seed", type=int, default=20260713)
    prepare_functional.add_argument("--force", action="store_true")

    prepare_diagnostic = subparsers.add_parser("prepare-diagnostic")
    prepare_diagnostic.add_argument("--input", action="append", required=True)
    prepare_diagnostic.add_argument("--output-dir", required=True)
    prepare_diagnostic.add_argument("--seed", type=int, default=20260713)
    prepare_diagnostic.add_argument("--reviewer-1", required=True)
    prepare_diagnostic.add_argument("--reviewer-2", required=True)
    prepare_diagnostic.add_argument("--force", action="store_true")

    profile_diagnostic = subparsers.add_parser("profile-diagnostic")
    profile_diagnostic.add_argument("--input", action="append", required=True)
    profile_diagnostic.add_argument("--seed", type=int, default=20260713)

    validate_diagnostic = subparsers.add_parser("validate-diagnostic")
    validate_diagnostic.add_argument("--packets", required=True)
    validate_diagnostic.add_argument("--responses", required=True)

    analyze_diagnostic = subparsers.add_parser("analyze-diagnostic")
    analyze_diagnostic.add_argument("--packets-1", required=True)
    analyze_diagnostic.add_argument("--mapping-1", required=True)
    analyze_diagnostic.add_argument("--responses-1", required=True)
    analyze_diagnostic.add_argument("--packets-2", required=True)
    analyze_diagnostic.add_argument("--mapping-2", required=True)
    analyze_diagnostic.add_argument("--responses-2", required=True)
    analyze_diagnostic.add_argument("--judge-observations", required=True)
    analyze_diagnostic.add_argument("--adjudications")
    analyze_diagnostic.add_argument("--functional-result", required=True)
    analyze_diagnostic.add_argument("--output-json", required=True)
    analyze_diagnostic.add_argument("--output-report", required=True)
    analyze_diagnostic.add_argument("--force", action="store_true")

    judge_functional = subparsers.add_parser("judge-functional")
    judge_functional.add_argument("--packets", required=True)
    judge_functional.add_argument("--output", required=True)
    judge_functional.add_argument("--model", required=True)
    judge_functional.add_argument("--force", action="store_true")

    judge_diagnostic = subparsers.add_parser("judge-diagnostic")
    judge_diagnostic.add_argument("--packets", required=True)
    judge_diagnostic.add_argument("--output", required=True)
    judge_diagnostic.add_argument("--model", required=True)
    judge_diagnostic.add_argument("--force", action="store_true")

    review_diagnostic = subparsers.add_parser("review-diagnostic")
    review_diagnostic.add_argument("--packets", required=True)
    review_diagnostic.add_argument("--responses", required=True)

    args = parser.parse_args()
    if args.command == "profile-diagnostic":
        profile = profile_diagnostic_cohort(
            _load_jsonl_many(args.input), seed=args.seed
        )
        print(json.dumps(profile, ensure_ascii=False))
        if profile["status"] != "ready":
            raise SystemExit(1)
        return

    if args.command == "prepare-functional":
        manifest = prepare_functional_judge_files(
            args.input,
            args.output_dir,
            seed=args.seed,
            force=args.force,
        )
        print(json.dumps(manifest, ensure_ascii=False))
        return

    if args.command == "prepare-diagnostic":
        try:
            manifest = prepare_diagnostic_review_files(
                args.input,
                args.output_dir,
                seed=args.seed,
                reviewer_1=args.reviewer_1,
                reviewer_2=args.reviewer_2,
                force=args.force,
            )
        except CohortNotReadyError as exc:
            print(json.dumps(exc.profile, ensure_ascii=False))
            raise SystemExit(1) from None
        print(json.dumps(manifest, ensure_ascii=False))
        return

    if args.command == "validate-diagnostic":
        packets = load_jsonl(Path(args.packets))
        responses = load_jsonl(Path(args.responses))
        errors = validate_diagnostic_responses(packets, responses)
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False))
        if errors:
            raise SystemExit(1)
        return

    if args.command == "analyze-diagnostic":
        _run_diagnostic_analysis(args)
        return

    if args.command == "judge-diagnostic":
        packets = load_jsonl(Path(args.packets))
        output = Path(args.output)
        ensure_outputs_available([output], force=args.force)
        observations = run_diagnostic_judge(packets, model=args.model)
        observation_errors = validate_diagnostic_judge_observations(
            packets, observations
        )
        if observation_errors:
            raise ValueError(
                "invalid diagnostic Judge observations: "
                + "; ".join(observation_errors)
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(output, observations)
        print(json.dumps({"observations": len(observations)}, ensure_ascii=False))
        return

    if args.command == "review-diagnostic":
        run_diagnostic_review_server(args.packets, args.responses)
        return

    if args.command != "judge-functional":
        raise ValueError(f"unsupported calibration command: {args.command}")
    packets = load_jsonl(Path(args.packets))
    output = Path(args.output)
    ensure_outputs_available([output], force=args.force)
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


def _run_diagnostic_analysis(args: argparse.Namespace) -> None:
    output_json = Path(args.output_json)
    output_report = Path(args.output_report)
    ensure_outputs_available([output_json, output_report], force=args.force)
    analysis = analyze_diagnostic_study(
        functional_result=_load_json_object(args.functional_result),
        packets_1=load_jsonl(Path(args.packets_1)),
        mapping_1=load_jsonl(Path(args.mapping_1)),
        responses_1=load_jsonl(Path(args.responses_1)),
        packets_2=load_jsonl(Path(args.packets_2)),
        mapping_2=load_jsonl(Path(args.mapping_2)),
        responses_2=load_jsonl(Path(args.responses_2)),
        judge_observations=load_jsonl(Path(args.judge_observations)),
        adjudications=_optional_jsonl(args.adjudications),
    )
    input_paths = {
        "packets_round_1": args.packets_1,
        "mapping_round_1": args.mapping_1,
        "responses_round_1": args.responses_1,
        "packets_round_2": args.packets_2,
        "mapping_round_2": args.mapping_2,
        "responses_round_2": args.responses_2,
        "judge_observations": args.judge_observations,
        "functional_result": args.functional_result,
    }
    if args.adjudications:
        input_paths["adjudications"] = args.adjudications
    analysis["input_artifacts"] = {
        name: {"path": path, "sha256": file_sha256(Path(path))}
        for name, path in input_paths.items()
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_report.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output_report.write_text(render_diagnostic_report(analysis), encoding="utf-8")
    print(json.dumps({"status": analysis["status"]}, ensure_ascii=False))


def _optional_jsonl(path: str | None) -> list[dict[str, Any]] | None:
    return load_jsonl(Path(path)) if path else None


def _load_jsonl_many(paths: list[str]) -> list[dict[str, Any]]:
    return [record for path in paths for record in load_jsonl(Path(path))]


def _load_json_object(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


if __name__ == "__main__":
    main()
