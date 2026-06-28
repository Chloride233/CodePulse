"""Reasoning quality grader for process dimension evaluation.

Evaluates the quality of an agent's reasoning steps using an LLM judge.
Assesses logical completeness, correctness of the reasoning chain, and
appropriate use of information. Targets the PROCESS dimension.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from codepulse.eval.llm_judge import call_llm_with_retry
from codepulse.eval.scoring import ScoreDimension

if TYPE_CHECKING:
    from codepulse.data.models import Task, Trial
    from codepulse.data.protocols import GraderResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert code review evaluator specializing in reasoning quality analysis.

Your task is to evaluate the quality of an AI agent's reasoning steps when solving a coding task.

Evaluation criteria (1-5 scale):
5 - Excellent: All reasoning steps are logically complete, form a correct chain, and make appropriate use of the given information
4 - Good: Reasoning is mostly complete with minor gaps, chain is sound, information usage is appropriate
3 - Adequate: Reasoning has some gaps or minor logical issues, but the general approach is reasonable
2 - Poor: Reasoning has significant gaps, logical errors, or misuses given information
1 - Very Poor: Reasoning is fundamentally flawed, missing, or entirely inappropriate

You MUST respond with valid JSON only, no other text:
{{"score": <1-5 integer>, "reasoning": "<your detailed evaluation>"}}
"""

_USER_PROMPT = """\
## Task Description

{task_description}

## Agent Reasoning Steps

{reasoning_steps}
"""


def _format_reasoning_steps(steps: list[str]) -> str:
    """Format reasoning steps list into a readable numbered string.

    Args:
        steps: List of reasoning step strings.

    Returns:
        Formatted string with numbered steps, or a placeholder if empty.
    """
    if not steps:
        return "(No reasoning steps provided)"
    return "\n".join(f"Step {i}: {step}" for i, step in enumerate(steps, 1))


def _build_task_description(task_input: dict[str, object]) -> str:
    """Build a task description string from task input dict.

    Extracts description and any available context from the task input.

    Args:
        task_input: The task's input dictionary.

    Returns:
        A formatted task description string.
    """
    parts: list[str] = []
    description = task_input.get("description")
    if description:
        parts.append(str(description))

    context = task_input.get("context")
    if context:
        parts.append(f"\n### Context\n{context}")

    return "\n".join(parts) if parts else "(No task description available)"


@dataclass
class ReasoningGrader:
    """Grade reasoning quality using an LLM judge.

    Evaluates an agent's reasoning steps against three criteria:
    - Logical completeness: Are all necessary steps present?
    - Correct reasoning chain: Do the steps follow logically?
    - Appropriate use of information: Is task information used well?

    Attributes:
        name: Identifier for this grader.
        model: LiteLLM model identifier for the judge LLM.
    """

    name: str = "reasoning"
    model: str = "deepseek-chat"

    def grade(self, task: Task, trial: Trial) -> GraderResult:
        """Evaluate reasoning quality of a trial.

        Extracts reasoning steps from the trial outcome, builds an evaluation
        prompt, and calls the LLM to score reasoning quality on a 1-5 scale.
        The score is normalized to [0, 1] by dividing by 5.

        If no reasoning steps are found in the trial outcome, returns a score
        of 0 immediately without calling the LLM.

        On any failure (LLM error, unparseable response) the method returns a
        score of 0 with error details instead of raising.

        Args:
            task: The original task definition containing input data.
            trial: The agent's execution trial containing outcome data.

        Returns:
            :class:`GraderResult` with dimension ``PROCESS``.
        """
        from codepulse.data.protocols import GraderResult

        reasoning_steps = trial.outcome.get("reasoning_steps", [])

        if not reasoning_steps:
            logger.info(
                "No reasoning steps found in trial %s, returning score 0",
                trial.trial_id,
            )
            return GraderResult(
                dimension=ScoreDimension.PROCESS,
                score=0.0,
                details={
                    "error": "no reasoning steps found",
                    "model": self.model,
                },
                evidence=[{"kind": "step_count", "value": 0}],
                diagnosis="缺少可审查的 reasoning steps，无法判断过程质量。",
            )

        task_description = _build_task_description(task.input)
        formatted_steps = _format_reasoning_steps(reasoning_steps)

        system_prompt = _SYSTEM_PROMPT
        user_prompt = _USER_PROMPT.format(
            task_description=task_description,
            reasoning_steps=formatted_steps,
        )

        try:
            raw = call_llm_with_retry(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
            )
            if raw is None:
                raise RuntimeError("LLM call failed after retries")
        except Exception:
            logger.exception("LLM call failed in ReasoningGrader")
            return GraderResult(
                dimension=ScoreDimension.PROCESS,
                score=0.0,
                details={"error": "LLM call failed", "model": self.model},
                evidence=[{"kind": "judge_model", "value": self.model}],
                diagnosis="Reasoning judge 调用失败，需检查模型或网络配置。",
            )

        try:
            parsed = json.loads(raw)
            raw_score = int(parsed["score"])
            reasoning = str(parsed.get("reasoning", ""))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning(
                "Failed to parse ReasoningGrader LLM response: %s", raw
            )
            return GraderResult(
                dimension=ScoreDimension.PROCESS,
                score=0.0,
                details={
                    "error": "unparseable LLM response",
                    "raw_response": raw,
                    "model": self.model,
                },
                evidence=[{"kind": "raw_response", "value": raw[:200]}],
                diagnosis="Reasoning judge 返回不可解析结果，需收紧输出格式。",
            )

        clamped_score = max(1, min(5, raw_score))
        normalized = round(clamped_score / 5.0, 4)

        return GraderResult(
            dimension=ScoreDimension.PROCESS,
            score=normalized,
            details={
                "raw_score": clamped_score,
                "reasoning": reasoning,
                "step_count": len(reasoning_steps),
                "model": self.model,
            },
            evidence=[
                {"kind": "raw_score", "value": clamped_score},
                {"kind": "step_count", "value": len(reasoning_steps)},
            ],
            diagnosis=reasoning,
        )
