"""Run a CodePulse Agent against official SWE-bench repository environments."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from docker.errors import ImageNotFound

from codepulse.agent.adapter import (
    AgentProfile,
    _is_provider_auth_error,
    _load_agent_class,
    _serialize_transcript,
)
from codepulse.data.models import Difficulty, Task, TaskCategory, TaskSource
from codepulse.env.sandbox import Container, ResourceLimits, SandboxManager
from codepulse.eval.artifacts import canonical_sha256, file_sha256

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class OfficialHarness:
    """Official SWE-bench operations used by a single repository trial."""

    make_test_spec: Callable[..., Any]
    build_container: Callable[..., Any]
    setup_logger: Callable[..., Any]
    close_logger: Callable[..., Any]
    copy_to_container: Callable[..., Any]
    exec_run_with_timeout: Callable[..., Any]
    get_eval_report: Callable[..., Any]


@dataclass(frozen=True)
class SWEbenchTrial:
    """Observable result of one Agent attempt on an official SWE-bench instance."""

    success: bool
    outcome: dict[str, Any]
    metrics: dict[str, Any]


def load_swebench_instances(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load a frozen SWE-bench JSONL snapshot keyed by instance ID."""
    rows = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not all(isinstance(row, dict) and isinstance(row.get("instance_id"), str) for row in rows):
        raise ValueError("SWE-bench snapshot must contain object records with instance_id")
    instances = {str(row["instance_id"]): row for row in rows}
    if len(instances) != len(rows):
        raise ValueError("SWE-bench snapshot contains duplicate instance IDs")
    return instances


def validate_swebench_training_manifest(
    manifest: dict[str, Any], repo_root: str | Path
) -> list[str]:
    """Return frozen-training manifest validation errors without invoking Docker."""
    root = Path(repo_root)
    errors: list[str] = []
    if manifest.get("protocol_version") != "phase3-swebench-training-v1":
        errors.append("protocol_version must equal 'phase3-swebench-training-v1'")
    if manifest.get("benchmark") != "swe-bench-verified":
        errors.append("benchmark must equal 'swe-bench-verified'")
    if manifest.get("n_trials") != 1:
        errors.append("n_trials must equal 1")
    if manifest.get("seed") != 20260717:
        errors.append("seed must equal 20260717")
    task_ids = manifest.get("task_ids")
    if not isinstance(task_ids, list) or len(task_ids) != 5 or len(set(task_ids)) != 5:
        errors.append("task_ids must contain exactly five unique training instances")
    dataset = manifest.get("dataset")
    if not isinstance(dataset, dict):
        return errors + ["dataset must be an object"]
    path = dataset.get("task_path")
    digest = dataset.get("task_sha256")
    if not isinstance(path, str) or not isinstance(digest, str):
        return errors + ["dataset.task_path and dataset.task_sha256 are required"]
    snapshot = root / path
    if not snapshot.is_file():
        return errors + [f"dataset.task_path does not exist: {path}"]
    if file_sha256(snapshot) != digest:
        errors.append(f"dataset.task_sha256 mismatch for {path}")
    try:
        instances = load_swebench_instances(snapshot)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return errors + [f"dataset snapshot cannot be loaded: {exc}"]
    if isinstance(task_ids, list) and any(task_id not in instances for task_id in task_ids):
        errors.append("task_ids must all exist in the frozen SWE-bench snapshot")
    agents = manifest.get("agents")
    if not isinstance(agents, list) or len(agents) != 1 or not isinstance(agents[0], dict):
        return errors + ["agents must contain exactly one baseline entry"]
    agent = agents[0]
    if agent.get("role") != "baseline":
        errors.append("training agent role must equal 'baseline'")
    profile_path = agent.get("profile_path")
    profile_digest = agent.get("profile_sha256")
    if not isinstance(profile_path, str) or not isinstance(profile_digest, str):
        return errors + ["baseline profile_path and profile_sha256 are required"]
    profile = root / profile_path
    if not profile.is_file():
        errors.append(f"baseline profile_path does not exist: {profile_path}")
    elif file_sha256(profile) != profile_digest:
        errors.append(f"baseline profile_sha256 mismatch for {profile_path}")
    runner = manifest.get("runner")
    if not isinstance(runner, dict):
        return errors + ["runner must be an object"]
    if runner.get("harness_version") != "swebench==4.1.0":
        errors.append("runner.harness_version must equal 'swebench==4.1.0'")
    if runner.get("architecture") != "x86_64":
        errors.append("runner.architecture must equal 'x86_64'")
    if runner.get("image_namespace") != "swebench":
        errors.append("runner.image_namespace must equal 'swebench'")
    if runner.get("timeout_seconds") != 900:
        errors.append("runner.timeout_seconds must equal 900")
    if runner.get("cpu_count") != 2:
        errors.append("runner.cpu_count must equal 2")
    if runner.get("memory_mb") != 4096:
        errors.append("runner.memory_mb must equal 4096")
    if runner.get("network") != "none":
        errors.append("runner.network must equal 'none'")
    image_digests = runner.get("image_digests")
    if not isinstance(image_digests, dict) or set(image_digests) != set(task_ids or []):
        errors.append("runner.image_digests must cover exactly the frozen task_ids")
    elif not all(
        isinstance(digest, str)
        and digest.startswith("sha256:")
        and len(digest) == 71
        and all(character in "0123456789abcdef" for character in digest[7:])
        for digest in image_digests.values()
    ):
        errors.append("runner.image_digests values must be sha256 digests")
    if manifest.get("budget") != {
        "total_cny": 20.0,
        "per_agent_cny": 20.0,
        "per_trial_cny": 4.0,
    }:
        errors.append("budget must equal the frozen SWE-bench training limits")
    return errors


def run_swebench_trial(
    profile: AgentProfile,
    instance: dict[str, Any],
    sandbox: SandboxManager,
    *,
    timeout_seconds: int,
    architecture: str,
    image_namespace: str,
    image_digest: str,
    cpu_count: int,
    memory_mb: int,
) -> SWEbenchTrial:
    """Run one Agent in an official repository image and grade its submitted patch."""
    harness = _official_harness()
    test_spec = harness.make_test_spec(
        instance,
        namespace=image_namespace,
        arch=architecture,
    )
    client = sandbox._client
    image_ref = _prepare_official_image(client, test_spec, image_digest)
    log_path = Path("results") / "swebench-harness" / str(instance["instance_id"]) / "agent.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = harness.setup_logger(str(instance["instance_id"]), log_path)
    official_container = None
    try:
        official_container = harness.build_container(
            test_spec, client, "codepulse", logger, False, False
        )
        _start_isolated_container(client, official_container, cpu_count, memory_mb)
        container = Container(
            id=str(official_container.id),
            image=str(test_spec.instance_image_key),
            resource_limits=ResourceLimits(
                cpu_count=cpu_count,
                memory_mb=memory_mb,
                timeout_seconds=timeout_seconds,
            ),
        )
        _bind_workspace(sandbox, container)
        task = _task_from_instance(instance)
        agent = _load_agent_class(profile)
        sandbox.set_active_container(container)
        transcript = agent.run(task, sandbox)
        sandbox.clear_active_container()
        error_event = next(
            (event for event in reversed(transcript.events) if event.event_type == "error"),
            None,
        )
        failure_type = None
        if error_event is not None:
            failure_type = (
                "provider_auth_error"
                if _is_provider_auth_error(error_event.content)
                else "provider_error"
            )
        patch_result = sandbox.execute(container, "cd /testbed && git diff")
        report, test_output = _evaluate_patch(
            harness, official_container, test_spec, instance, patch_result.stdout, timeout_seconds
        )
        resolved = bool(report.get(str(instance["instance_id"]), {}).get("resolved", False))
        return SWEbenchTrial(
            success=resolved,
            outcome={
                "official_resolved": resolved,
                "official_report": report,
                "instance_image": image_ref,
                "patch": patch_result.stdout,
                "patch_sha256": canonical_sha256(patch_result.stdout),
                "test_output": test_output[:4096],
                "trace": _serialize_transcript(transcript),
                "failure_type": failure_type,
                "provider_model_versions": transcript.agent_config.get(
                    "provider_model_versions", []
                ),
            },
            metrics={
                "input_tokens": int(transcript.agent_config.get("input_tokens", 0)),
                "output_tokens": int(transcript.agent_config.get("output_tokens", 0)),
                "cache_tokens": int(transcript.agent_config.get("cache_tokens", 0)),
                "total_tokens": transcript.total_tokens,
                "duration_seconds": transcript.total_duration,
                "cost_usd": float(transcript.agent_config.get("cost_usd", 0.0)),
            },
        )
    finally:
        sandbox.clear_active_container()
        if official_container is not None:
            official_container.remove(force=True)
        harness.close_logger(logger)


def _prepare_official_image(client: Any, test_spec: Any, digest: str) -> str:
    """Pull the frozen official image by digest and expose its expected local tag."""
    repository, tag = str(test_spec.instance_image_key).rsplit(":", 1)
    image_ref = f"{repository}@{digest}"
    try:
        image = client.images.get(image_ref)
    except ImageNotFound:
        image = client.images.pull(image_ref)
    image.tag(repository, tag=tag)
    return image_ref


def _start_isolated_container(
    client: Any, official_container: Any, cpu_count: int, memory_mb: int
) -> None:
    """Apply frozen resource limits and remove every Docker network attachment."""
    official_container.update(
        cpu_period=100_000,
        cpu_quota=cpu_count * 100_000,
        mem_limit=f"{memory_mb}m",
        memswap_limit=f"{memory_mb}m",
    )
    official_container.start()
    official_container.reload()
    networks = official_container.attrs.get("NetworkSettings", {}).get("Networks", {})
    for network_name in networks:
        client.networks.get(network_name).disconnect(official_container, force=True)


def _task_from_instance(instance: dict[str, Any]) -> Task:
    """Expose only the issue context to the Agent, never the oracle patch or tests."""
    return Task(
        task_id=str(instance["instance_id"]),
        source=TaskSource.SWE_BENCH,
        category=TaskCategory.BUG_FIX,
        difficulty=Difficulty.MEDIUM,
        language="python",
        input={"description": str(instance["problem_statement"])},
        ground_truth={},
        metadata={
            "repo": str(instance["repo"]),
            "base_commit": str(instance["base_commit"]),
        },
    )


def _bind_workspace(sandbox: SandboxManager, container: Container) -> None:
    """Map the Agent's existing /workspace tools onto the official /testbed repo."""
    result = sandbox.execute(
        container, "test -d /testbed && (test -e /workspace || ln -s /testbed /workspace)"
    )
    if result.exit_code != 0:
        raise RuntimeError("official SWE-bench container does not expose /testbed")


def _evaluate_patch(
    harness: OfficialHarness,
    official_container: Any,
    test_spec: Any,
    instance: dict[str, Any],
    patch: str,
    timeout_seconds: int,
) -> tuple[dict[str, Any], str]:
    """Run the official evaluation script against the Agent-generated patch."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        patch_path = root / "patch.diff"
        eval_path = root / "eval.sh"
        output_path = root / "test_output.txt"
        patch_path.write_text(patch, encoding="utf-8")
        eval_path.write_text(str(test_spec.eval_script), encoding="utf-8")
        harness.copy_to_container(official_container, patch_path, PurePosixPath("/tmp/patch.diff"))
        apply_result = official_container.exec_run(
            "git reset --hard HEAD && git clean -fd && git apply --verbose /tmp/patch.diff",
            workdir="/testbed",
            user="root",
        )
        if apply_result.exit_code != 0:
            return {}, apply_result.output.decode("utf-8", errors="replace")
        harness.copy_to_container(official_container, eval_path, PurePosixPath("/eval.sh"))
        test_output, timed_out, _ = harness.exec_run_with_timeout(
            official_container, "/bin/bash /eval.sh", timeout_seconds
        )
        if timed_out:
            return {}, test_output + f"\nTimeout after {timeout_seconds}s"
        output_path.write_text(test_output, encoding="utf-8")
        prediction = {
            "instance_id": str(instance["instance_id"]),
            "model_name_or_path": "codepulse",
            "model_patch": patch,
        }
        return harness.get_eval_report(test_spec, prediction, output_path), test_output


def _official_harness() -> OfficialHarness:
    """Load the official harness lazily so core CodePulse stays lightweight."""
    try:
        from swebench.harness.docker_build import (  # type: ignore[import-untyped]
            build_container,
            close_logger,
            setup_logger,
        )
        from swebench.harness.docker_utils import (  # type: ignore[import-untyped]
            copy_to_container,
            exec_run_with_timeout,
        )
        from swebench.harness.grading import get_eval_report  # type: ignore[import-untyped]
        from swebench.harness.test_spec import test_spec  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "SWE-bench support requires `pip install -e '.[swebench]'`"
        ) from exc
    return OfficialHarness(
        make_test_spec=test_spec.make_test_spec,
        build_container=build_container,
        setup_logger=setup_logger,
        close_logger=close_logger,
        copy_to_container=copy_to_container,
        exec_run_with_timeout=exec_run_with_timeout,
        get_eval_report=get_eval_report,
    )
