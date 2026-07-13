"""Full-evidence packet preparation for qualitative Judge calibration."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from codepulse.eval.artifacts import (
    canonical_sha256,
    ensure_outputs_available,
    file_sha256,
    load_jsonl,
    write_jsonl,
)
from codepulse.eval.calibration_cohort import (
    select_diagnostic_cohort,
    validate_diagnostic_trial,
)

DIAGNOSTIC_RUBRIC_VERSION = "diagnostic-process-v1"
DIAGNOSTIC_PACKET_VERSION = "diagnostic-review-packet-v1"
_IDENTITY_KEYS = {
    "agent_config",
    "agent_name",
    "model",
    "provider_model",
    "provider_model_versions",
    "session_id",
}
_RESPONSE_KEYS = (
    "packet_id",
    "round",
    "rubric_version",
    "packet_sha256",
)


def build_diagnostic_packets(
    trials: list[dict[str, Any]],
    *,
    round_number: int,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build one seeded identity-blind round from eligible full-evidence trials."""
    if round_number < 1:
        raise ValueError("round_number must be positive")
    if len(trials) < 10:
        raise ValueError("at least 10 diagnostic trials are required")

    trial_ids = [str(trial.get("trial_id", "")) for trial in trials]
    duplicates = sorted(key for key, count in Counter(trial_ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate diagnostic trial IDs: {', '.join(duplicates)}")

    packets: list[dict[str, Any]] = []
    mapping_by_packet: dict[str, dict[str, Any]] = {}
    for index, trial in enumerate(trials):
        errors = validate_diagnostic_trial(trial, index)
        if errors:
            raise ValueError("invalid diagnostic trial: " + "; ".join(errors))

        trial_id = str(trial["trial_id"])
        packet_id = "diag-" + hashlib.sha256(
            f"{seed}:{round_number}:{trial_id}".encode()
        ).hexdigest()[:16]
        outcome = trial["outcome"]
        evidence = outcome["evidence"]
        transcript = evidence["transcript"]
        packet: dict[str, Any] = {
            "schema_version": DIAGNOSTIC_PACKET_VERSION,
            "packet_id": packet_id,
            "round": round_number,
            "rubric_version": DIAGNOSTIC_RUBRIC_VERSION,
            "dimension": "process_quality",
            "evidence": {
                "task": {
                    key: value
                    for key, value in evidence["task"].items()
                    if key != "task_id"
                },
                "final_code": evidence["output_files"]["solution.py"],
                "trace": {
                    "events": _strip_identity(transcript["events"]),
                    "total_tokens": transcript["total_tokens"],
                    "total_duration": transcript["total_duration"],
                    "tool_call_count": transcript["tool_call_count"],
                },
                "verification": evidence["verification"],
                "metrics": _diagnostic_metrics(trial["metrics"]),
            },
        }
        packet["packet_sha256"] = canonical_sha256(packet)
        packets.append(packet)
        mapping_by_packet[packet_id] = {
            "packet_id": packet_id,
            "trial_id": trial_id,
            "task_id": trial["task_id"],
            "agent_name": trial["agent_name"],
            "provider_model_versions": trial.get("provider_model_versions", []),
            "source_evidence_sha256": evidence["sha256"],
            "source_record_sha256": canonical_sha256(trial),
        }

    random.Random(seed + round_number).shuffle(packets)
    mapping = [mapping_by_packet[str(packet["packet_id"])] for packet in packets]
    return packets, mapping


def build_diagnostic_response_template(
    packets: list[dict[str, Any]], reviewer_id: str
) -> list[dict[str, Any]]:
    """Create an unscored 1-5 response template for one diagnostic round."""
    if not reviewer_id.strip():
        raise ValueError("reviewer_id is required")
    return [
        {
            "packet_id": packet["packet_id"],
            "round": packet["round"],
            "reviewer_id": reviewer_id,
            "rubric_version": packet["rubric_version"],
            "score": None,
            "rationale": None,
            "reviewed_at": None,
            "packet_sha256": packet["packet_sha256"],
        }
        for packet in packets
    ]


def validate_diagnostic_packets(packets: list[dict[str, Any]]) -> list[str]:
    """Validate diagnostic hashes, evidence completeness, and identity blinding."""
    errors: list[str] = []
    ids = [str(packet.get("packet_id", "")) for packet in packets]
    duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate packet IDs: {', '.join(duplicates)}")

    for index, packet in enumerate(packets):
        packet_id = str(packet.get("packet_id", f"index-{index}"))
        supplied_hash = packet.get("packet_sha256")
        unhashed = {key: value for key, value in packet.items() if key != "packet_sha256"}
        if supplied_hash != canonical_sha256(unhashed):
            errors.append(f"packet {packet_id} hash mismatch")
        if packet.get("schema_version") != DIAGNOSTIC_PACKET_VERSION:
            errors.append(f"packet {packet_id} has unknown schema version")
        if packet.get("rubric_version") != DIAGNOSTIC_RUBRIC_VERSION:
            errors.append(f"packet {packet_id} has unknown rubric version")
        if packet.get("dimension") != "process_quality":
            errors.append(f"packet {packet_id} has ineligible dimension")
        forbidden = sorted(_find_identity_keys(packet))
        if forbidden:
            errors.append(
                f"packet {packet_id} leaks identity keys: {', '.join(forbidden)}"
            )
        errors.extend(_validate_packet_evidence(packet_id, packet.get("evidence")))
    return errors


def validate_diagnostic_responses(
    packets: list[dict[str, Any]], responses: list[dict[str, Any]]
) -> list[str]:
    """Validate a complete diagnostic human review round."""
    errors = validate_diagnostic_packets(packets)
    packet_by_id = {str(packet["packet_id"]): packet for packet in packets}
    response_ids = [str(response.get("packet_id", "")) for response in responses]
    if Counter(response_ids) != Counter(packet_by_id.keys()):
        errors.append("response coverage does not match diagnostic packets")

    for response in responses:
        packet_id = str(response.get("packet_id", ""))
        packet = packet_by_id.get(packet_id)
        if packet is None:
            errors.append(f"response references unknown packet {packet_id}")
            continue
        for key in _RESPONSE_KEYS:
            if response.get(key) != packet.get(key):
                errors.append(f"response {packet_id} {key} mismatch")
        score = response.get("score")
        if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
            errors.append(f"response {packet_id} has invalid score")
        if not _nonempty_string(response.get("reviewer_id")):
            errors.append(f"response {packet_id} requires reviewer_id")
        if not _nonempty_string(response.get("rationale")):
            errors.append(f"response {packet_id} requires rationale")
        if not _nonempty_string(response.get("reviewed_at")):
            errors.append(f"response {packet_id} requires reviewed_at")
    return errors


def prepare_diagnostic_review_files(
    source_path: str | Path,
    output_dir: str | Path,
    *,
    seed: int,
    reviewer_1: str,
    reviewer_2: str,
    force: bool = False,
) -> dict[str, Any]:
    """Write two diagnostic blind rounds, private mappings, and response templates."""
    source = Path(source_path)
    output = Path(output_dir)
    candidate_trials = load_jsonl(source)
    trials, cohort_profile = select_diagnostic_cohort(candidate_trials, seed=seed)
    round_1, mapping_1 = build_diagnostic_packets(
        trials, round_number=1, seed=seed
    )
    round_2, mapping_2 = build_diagnostic_packets(
        trials, round_number=2, seed=seed
    )
    artifacts: dict[str, list[dict[str, Any]]] = {
        "review-packets-round-1.jsonl": round_1,
        "review-packets-round-2.jsonl": round_2,
        "review-mapping-round-1.private.jsonl": mapping_1,
        "review-mapping-round-2.private.jsonl": mapping_2,
        "human-review-round-1.jsonl": build_diagnostic_response_template(
            round_1, reviewer_1
        ),
        "human-review-round-2.jsonl": build_diagnostic_response_template(
            round_2, reviewer_2
        ),
    }
    targets = [output / name for name in artifacts]
    targets.append(output / "manifest.json")
    ensure_outputs_available(targets, force=force)

    output.mkdir(parents=True, exist_ok=True)
    artifact_hashes: dict[str, str] = {}
    for name, rows in artifacts.items():
        path = output / name
        write_jsonl(path, rows)
        artifact_hashes[name] = file_sha256(path)

    manifest: dict[str, Any] = {
        "protocol_version": "diagnostic-study-v1",
        "status": "review_prepared",
        "source": str(source),
        "source_sha256": file_sha256(source),
        "candidate_pool_size": len(candidate_trials),
        "sample_size": len(trials),
        "seed": seed,
        "rubric_version": DIAGNOSTIC_RUBRIC_VERSION,
        "reviewer_mode": (
            "inter_rater" if reviewer_1 != reviewer_2 else "intra_rater"
        ),
        "cohort_profile": cohort_profile,
        "artifact_hashes": artifact_hashes,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _validate_packet_evidence(packet_id: str, evidence: object) -> list[str]:
    if not isinstance(evidence, dict):
        return [f"packet {packet_id} requires evidence"]
    errors: list[str] = []
    task = evidence.get("task")
    if not isinstance(task, dict) or not _nonempty_string(task.get("description")):
        errors.append(f"packet {packet_id} requires task description")
    if not _nonempty_string(evidence.get("final_code")):
        errors.append(f"packet {packet_id} requires final code")
    trace = evidence.get("trace")
    if not isinstance(trace, dict) or not isinstance(trace.get("events"), list) or not trace.get("events"):
        errors.append(f"packet {packet_id} requires a non-empty Trace")
    if not _valid_verification(evidence.get("verification")):
        errors.append(f"packet {packet_id} requires complete verification")
    metrics = evidence.get("metrics")
    if not isinstance(metrics, dict) or not isinstance(metrics.get("total_tokens"), int):
        errors.append(f"packet {packet_id} requires token metrics")
    return errors


def _valid_verification(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    exit_code = value.get("exit_code")
    total = value.get("pytest_total")
    passed = value.get("pytest_passed")
    return (
        isinstance(exit_code, int)
        and not isinstance(exit_code, bool)
        and isinstance(total, int)
        and not isinstance(total, bool)
        and total > 0
        and isinstance(passed, int)
        and not isinstance(passed, bool)
        and 0 <= passed <= total
        and isinstance(value.get("stdout"), str)
        and isinstance(value.get("stderr"), str)
    )


def _diagnostic_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "input_tokens",
        "output_tokens",
        "cache_tokens",
        "total_tokens",
        "duration_seconds",
    )
    return {key: metrics[key] for key in keys if key in metrics}


def _strip_identity(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _strip_identity(child)
            for key, child in value.items()
            if key not in _IDENTITY_KEYS and key != "timestamp"
        }
    if isinstance(value, list):
        return [_strip_identity(child) for child in value]
    return value


def _find_identity_keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _IDENTITY_KEYS:
                found.add(key)
            found.update(_find_identity_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_find_identity_keys(child))
    return found


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
