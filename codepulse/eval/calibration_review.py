"""Deterministic functional-evidence packets and Judge I/O."""

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
from codepulse.eval.llm_judge import call_llm_with_retry

FUNCTIONAL_RUBRIC_VERSION = "functional-evidence-v1"
FUNCTIONAL_LABELS = {
    "supported_pass",
    "supported_fail",
    "insufficient_evidence",
}
JUDGE_STATUSES = {"ok", "missing"}
JUDGE_VARIANTS = {
    "identity_blind",
    "position_ab",
    "position_ba",
    "length_full",
    "length_compact",
}
FUNCTIONAL_JUDGE_PROMPT_VERSION = "functional-evidence-judge-v2"
_FORBIDDEN_REVIEW_KEYS = {
    "agent_name",
    "human_review_round_1",
    "human_review_round_2",
    "llm_judge",
    "model",
    "provider_model_versions",
    "scores",
    "source_trial_id",
    "stratum",
    "success",
}
_VERIFICATION_KEYS = {
    "exit_code",
    "mypy_errors",
    "pytest_passed",
    "pytest_total",
    "ruff_violations",
    "stderr",
    "stdout",
}
_FUNCTIONAL_JUDGE_SYSTEM_PROMPT = """\
You audit deterministic execution evidence. Choose exactly one label:
- supported_pass: official deterministic evidence reports a completed passing run.
- supported_fail: official deterministic evidence reports a failed or incomplete run.
- insufficient_evidence: evidence is missing or contradictory.

Do not infer code quality, reasoning quality, robustness, or user experience.
An artifact_status that reports missing final code or a missing full transcript is
expected for this functional-only sample. It limits non-functional review but does
not contradict an otherwise complete official verification result. Judge pass/fail
support from the verification fields alone.
Return JSON only: {"label":"<label>","reasoning":"<evidence-grounded reason>"}
"""


def build_review_packets(
    records: list[dict[str, Any]],
    *,
    round_number: int,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Build a seeded functional Judge packet set and private mapping."""
    if round_number < 1:
        raise ValueError("round_number must be positive")

    packets: list[dict[str, Any]] = []
    mapping_by_packet: dict[str, dict[str, str]] = {}
    for record in records:
        sample_id = str(record["sample_id"])
        packet_id = "pkt-" + hashlib.sha256(
            f"{seed}:{round_number}:{sample_id}".encode()
        ).hexdigest()[:16]
        deterministic = record.get("deterministic_evidence", {})
        outcome = deterministic.get("outcome", {}) if isinstance(deterministic, dict) else {}
        verification = (
            {key: outcome[key] for key in sorted(_VERIFICATION_KEYS) if key in outcome}
            if isinstance(outcome, dict)
            else {}
        )
        packet: dict[str, Any] = {
            "schema_version": "calibration-review-packet-v1",
            "packet_id": packet_id,
            "round": round_number,
            "rubric_version": FUNCTIONAL_RUBRIC_VERSION,
            "dimension": "functional_evidence",
            "task_id": str(record.get("task_id", "")),
            "evidence": {
                "verification": verification,
                "artifact_status": record.get("artifact_status", "unknown"),
                "eligible_dimensions": record.get("eligible_dimensions", []),
            },
        }
        packet["packet_sha256"] = canonical_sha256(packet)
        packets.append(packet)
        mapping_by_packet[packet_id] = {
            "packet_id": packet_id,
            "sample_id": sample_id,
            "source_record_sha256": canonical_sha256(record),
        }

    random.Random(seed + round_number).shuffle(packets)
    mapping = [mapping_by_packet[str(packet["packet_id"])] for packet in packets]
    return packets, mapping


def validate_review_packets(packets: list[dict[str, Any]]) -> list[str]:
    """Validate packet hashes, identities, and reviewer blinding."""
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
        forbidden = sorted(_find_forbidden_keys(packet))
        if forbidden:
            errors.append(
                f"packet {packet_id} contains forbidden review keys: {', '.join(forbidden)}"
            )
        if packet.get("rubric_version") != FUNCTIONAL_RUBRIC_VERSION:
            errors.append(f"packet {packet_id} has unknown rubric version")
        if packet.get("dimension") != "functional_evidence":
            errors.append(f"packet {packet_id} has ineligible dimension")
    return errors


def validate_judge_observations(
    packets: list[dict[str, Any]], observations: list[dict[str, Any]]
) -> list[str]:
    """Validate Judge results while preserving call failures as missing values."""
    errors = validate_review_packets(packets)
    packet_by_id = {str(packet["packet_id"]): packet for packet in packets}
    seen: set[tuple[str, str, str]] = set()
    for observation in observations:
        packet_id = str(observation.get("packet_id", ""))
        judge_model = str(observation.get("judge_model", ""))
        variant = str(observation.get("variant", ""))
        key = (packet_id, judge_model, variant)
        if key in seen:
            errors.append(f"duplicate Judge observation: {key}")
        seen.add(key)

        packet = packet_by_id.get(packet_id)
        if packet is None:
            errors.append(f"Judge observation references unknown packet {packet_id}")
            continue
        if observation.get("packet_sha256") != packet["packet_sha256"]:
            errors.append(f"Judge observation {packet_id} packet hash mismatch")
        if not judge_model:
            errors.append(f"Judge observation {packet_id} requires judge_model")
        if variant not in JUDGE_VARIANTS:
            errors.append(f"Judge observation {packet_id} has invalid variant")

        status = observation.get("status")
        if status not in JUDGE_STATUSES:
            errors.append(f"Judge observation {packet_id} has invalid status")
        elif status == "missing":
            if any(
                observation.get(key) is not None
                for key in ("label", "score", "reasoning")
            ):
                errors.append(
                    f"missing observation {packet_id} must not contain a score or result"
                )
            if not _nonempty_string(observation.get("error")):
                errors.append(f"missing observation {packet_id} requires error evidence")
        elif not _valid_judge_result(observation):
            errors.append(f"Judge observation {packet_id} has invalid result")
    return errors


def prepare_functional_judge_files(
    source_path: str | Path,
    output_dir: str | Path,
    *,
    seed: int,
    force: bool = False,
) -> dict[str, Any]:
    """Write one deterministic functional Judge packet set and manifest."""
    source = Path(source_path)
    output = Path(output_dir)
    records = load_jsonl(source)
    packets, mapping = build_review_packets(records, round_number=1, seed=seed)
    artifacts: dict[str, list[dict[str, Any]]] = {
        "functional-packets.jsonl": packets,
        "functional-mapping.private.jsonl": mapping,
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
        "protocol_version": "functional-judge-study-v1",
        "status": "judge_prepared",
        "source": str(source),
        "source_sha256": file_sha256(source),
        "sample_size": len(records),
        "seed": seed,
        "rubric_version": FUNCTIONAL_RUBRIC_VERSION,
        "artifact_hashes": artifact_hashes,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def run_functional_judge(
    packets: list[dict[str, Any]], *, model: str
) -> list[dict[str, Any]]:
    """Run the identity-blind functional evidence Judge over review packets."""
    observations: list[dict[str, Any]] = []
    for packet in packets:
        raw = call_llm_with_retry(
            model=model,
            messages=[
                {"role": "system", "content": _FUNCTIONAL_JUDGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        packet["evidence"], ensure_ascii=False, sort_keys=True
                    ),
                },
            ],
            temperature=0.0,
        )
        common = {
            "packet_id": packet["packet_id"],
            "packet_sha256": packet["packet_sha256"],
            "judge_model": model,
            "variant": "identity_blind",
            "prompt_version": FUNCTIONAL_JUDGE_PROMPT_VERSION,
        }
        try:
            parsed = json.loads(raw) if raw is not None else None
            label = parsed["label"] if isinstance(parsed, dict) else None
            reasoning = parsed["reasoning"] if isinstance(parsed, dict) else None
            if label not in FUNCTIONAL_LABELS or not _nonempty_string(reasoning):
                raise ValueError("invalid Judge response schema")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            observations.append(
                {
                    **common,
                    "status": "missing",
                    "label": None,
                    "score": None,
                    "reasoning": None,
                    "raw_response": raw,
                    "error": "provider call failed" if raw is None else str(exc),
                }
            )
            continue
        observations.append(
            {
                **common,
                "status": "ok",
                "label": label,
                "score": None,
                "reasoning": reasoning,
                "raw_response": raw,
                "error": None,
            }
        )
    return observations


def _valid_judge_result(observation: dict[str, Any]) -> bool:
    label = observation.get("label")
    score = observation.get("score")
    has_result = label in FUNCTIONAL_LABELS or (
        isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 5
    )
    return (
        has_result
        and _nonempty_string(observation.get("reasoning"))
        and _nonempty_string(observation.get("raw_response"))
    )


def _find_forbidden_keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _FORBIDDEN_REVIEW_KEYS:
                found.add(key)
            found.update(_find_forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_find_forbidden_keys(child))
    return found


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
