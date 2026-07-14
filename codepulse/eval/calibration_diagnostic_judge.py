"""Qualitative Judge variants for full-evidence calibration packets."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from codepulse.eval.calibration_diagnostic import validate_diagnostic_packets
from codepulse.eval.llm_judge import call_llm_with_retry

DIAGNOSTIC_JUDGE_PROMPT_VERSION = "diagnostic-process-judge-v1"
DIAGNOSTIC_JUDGE_VARIANTS = ("length_full", "length_compact")
_DIAGNOSTIC_JUDGE_SYSTEM_PROMPT = """\
Score only the observable process quality in the supplied evidence on a 1-5 scale:
5: sound, direct, and fully supported by the final artifact and verification.
4: sound overall with a minor avoidable step or clarity gap.
3: adequate result with a material reasoning, tool-use, or recovery weakness.
2: major gaps, repeated ineffective work, or weak recovery despite some progress.
1: missing, fundamentally unsound, or unsupported observable process.

Do not infer hidden chain-of-thought, model identity, or unobserved behavior. Official
verification is authoritative for functional results, but process score must cite
observable Trace, tool use, recovery, or final artifact evidence.
Return JSON only: {"score":<integer 1-5>,"reasoning":"<evidence-grounded reason>"}
"""


def compact_diagnostic_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Project a full packet to a shorter Trace without changing authoritative fields."""
    trace = evidence["trace"]
    compact_events: list[dict[str, Any]] = []
    last_key: str | None = None
    for event in trace["events"]:
        projected = {
            "event_type": event.get("event_type"),
            "content": _compact_value(event.get("content", {})),
        }
        key = json.dumps(projected, ensure_ascii=False, sort_keys=True)
        if compact_events and key == last_key:
            compact_events[-1]["repeat_count"] = (
                int(compact_events[-1].get("repeat_count", 1)) + 1
            )
            continue
        compact_events.append(projected)
        last_key = key

    return {
        "task": evidence["task"],
        "final_code": evidence["final_code"],
        "trace": {
            "events": compact_events,
            "total_tokens": trace["total_tokens"],
            "total_duration": trace["total_duration"],
            "tool_call_count": trace["tool_call_count"],
        },
        "verification": evidence["verification"],
        "metrics": evidence["metrics"],
    }


def run_diagnostic_judge(
    packets: list[dict[str, Any]], *, model: str
) -> list[dict[str, Any]]:
    """Score full and compact evidence variants with one pinned Judge model."""
    packet_errors = validate_diagnostic_packets(packets)
    if packet_errors:
        raise ValueError("invalid diagnostic packets: " + "; ".join(packet_errors))

    observations: list[dict[str, Any]] = []
    for packet in packets:
        variants = {
            "length_full": packet["evidence"],
            "length_compact": compact_diagnostic_evidence(packet["evidence"]),
        }
        for variant in DIAGNOSTIC_JUDGE_VARIANTS:
            evidence = variants[variant]
            serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
            raw = call_llm_with_retry(
                model=model,
                messages=[
                    {"role": "system", "content": _DIAGNOSTIC_JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": serialized},
                ],
                temperature=0.0,
            )
            common = {
                "packet_id": packet["packet_id"],
                "packet_sha256": packet["packet_sha256"],
                "judge_model": model,
                "variant": variant,
                "prompt_version": DIAGNOSTIC_JUDGE_PROMPT_VERSION,
                "evidence_chars": len(serialized),
            }
            try:
                parsed = json.loads(raw) if raw is not None else None
                score = parsed["score"] if isinstance(parsed, dict) else None
                reasoning = parsed["reasoning"] if isinstance(parsed, dict) else None
                if (
                    not isinstance(score, int)
                    or isinstance(score, bool)
                    or not 1 <= score <= 5
                    or not _nonempty_string(reasoning)
                ):
                    raise ValueError("invalid diagnostic Judge response schema")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                observations.append(
                    {
                        **common,
                        "status": "missing",
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
                    "score": score,
                    "reasoning": reasoning,
                    "raw_response": raw,
                    "error": None,
                }
            )
    return observations


def validate_diagnostic_judge_observations(
    packets: list[dict[str, Any]], observations: list[dict[str, Any]]
) -> list[str]:
    """Validate full/compact observation coverage and strict Judge result fields."""
    errors = validate_diagnostic_packets(packets)
    packet_by_id = {str(packet["packet_id"]): packet for packet in packets}
    expected = {
        (packet_id, variant)
        for packet_id in packet_by_id
        for variant in DIAGNOSTIC_JUDGE_VARIANTS
    }
    keys = [
        (str(row.get("packet_id", "")), str(row.get("variant", "")))
        for row in observations
    ]
    duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate diagnostic Judge observations: {duplicates}")
    if set(keys) != expected:
        errors.append("diagnostic Judge observation coverage mismatch")

    for observation in observations:
        packet_id = str(observation.get("packet_id", ""))
        packet = packet_by_id.get(packet_id)
        if packet is None:
            errors.append(f"Judge observation references unknown packet {packet_id}")
            continue
        if observation.get("packet_sha256") != packet["packet_sha256"]:
            errors.append(f"Judge observation {packet_id} packet hash mismatch")
        if not _nonempty_string(observation.get("judge_model")):
            errors.append(f"Judge observation {packet_id} requires judge_model")
        if observation.get("variant") not in DIAGNOSTIC_JUDGE_VARIANTS:
            errors.append(f"Judge observation {packet_id} has invalid variant")
        if observation.get("prompt_version") != DIAGNOSTIC_JUDGE_PROMPT_VERSION:
            errors.append(f"Judge observation {packet_id} has unknown prompt version")
        evidence_chars = observation.get("evidence_chars")
        if (
            not isinstance(evidence_chars, int)
            or isinstance(evidence_chars, bool)
            or evidence_chars <= 0
        ):
            errors.append(f"Judge observation {packet_id} has invalid evidence length")

        status = observation.get("status")
        if status == "missing":
            if observation.get("score") is not None or observation.get("reasoning") is not None:
                errors.append(f"missing observation {packet_id} contains a result")
            if not _nonempty_string(observation.get("error")):
                errors.append(f"missing observation {packet_id} requires error evidence")
        elif status == "ok":
            score = observation.get("score")
            if (
                not isinstance(score, int)
                or isinstance(score, bool)
                or not 1 <= score <= 5
                or not _nonempty_string(observation.get("reasoning"))
                or not _nonempty_string(observation.get("raw_response"))
            ):
                errors.append(f"Judge observation {packet_id} has invalid result")
        else:
            errors.append(f"Judge observation {packet_id} has invalid status")
    return errors


def _compact_value(value: object) -> object:
    if isinstance(value, str):
        if len(value) <= 500:
            return value
        return value[:500] + f"\n...[{len(value) - 500} chars omitted]"
    if isinstance(value, dict):
        return {key: _compact_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_compact_value(child) for child in value]
    return value


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
