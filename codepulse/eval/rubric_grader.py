"""Rubric-based LLM judge grader for process quality evaluation.

Uses a configurable rubric to score agent output quality on a 1-5 scale
via an LLM call, normalized to [0, 1]. Targets the PROCESS dimension.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from codepulse.eval.scoring import ScoreDimension

if TYPE_CHECKING:
    from codepulse.data.models import Task, Trial
    from codepulse.data.protocols import GraderResult

logger = logging.getLogger(__name__)

DEFAULT_RUBRIC = """\
评分标准（1-5 分）：
5 分：代码逻辑完全正确，边界条件处理完善，无冗余
4 分：代码逻辑正确，少量边界遗漏，整体可维护
3 分：代码基本能用，有明显改进空间
2 分：代码有逻辑错误或严重质量问题
1 分：代码完全不可用
"""

_SYSTEM_PROMPT = """\
你是一个代码质量评审专家。请根据以下评分标准，对给定任务的代码输出进行评分。

{rubric}

请严格以 JSON 格式返回，不要包含任何其他内容：
{{"score": <1-5 的整数>, "reasoning": "<评分理由>"}}
"""

_USER_PROMPT = """\
## 任务描述

{description}

## 代码输出

{output}
"""


@dataclass
class RubricGrader:
    """Grade process quality using a rubric-based LLM judge.

    Attributes:
        name: Identifier for this grader.
        model: LiteLLM model identifier for the judge LLM.
        rubric: Scoring rubric prompt text.
    """

    name: str = "rubric"
    model: str = "deepseek-chat"
    rubric: str = field(default=DEFAULT_RUBRIC)

    def grade(self, task: Task, trial: Trial) -> GraderResult:
        """Evaluate a trial using the rubric-based LLM judge.

        Builds a prompt from the rubric, task description, and agent output,
        then calls the LLM to produce a 1-5 score with reasoning.  The score
        is normalized to [0, 1] by dividing by 5.

        On any failure (missing data, LLM error, unparseable response) the
        method returns a score of 0 with error details instead of raising.

        Args:
            task: The original task definition containing input["description"].
            trial: The agent's execution trial containing outcome["output"].

        Returns:
            :class:`GraderResult` with dimension ``PROCESS``.
        """
        from codepulse.data.protocols import GraderResult

        description = task.input.get("description", "")
        output = trial.outcome.get("output", "")

        system_prompt = _SYSTEM_PROMPT.format(rubric=self.rubric)
        user_prompt = _USER_PROMPT.format(description=description, output=output)

        try:
            import litellm

            response = litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
            )
            raw = response.choices[0].message.content or ""
        except Exception:
            logger.exception("LLM call failed in RubricGrader")
            return GraderResult(
                dimension=ScoreDimension.PROCESS,
                score=0.0,
                details={"error": "LLM call failed"},
            )

        try:
            parsed = json.loads(raw)
            raw_score = int(parsed["score"])
            reasoning = str(parsed.get("reasoning", ""))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning("Failed to parse RubricGrader LLM response: %s", raw)
            return GraderResult(
                dimension=ScoreDimension.PROCESS,
                score=0.0,
                details={"error": "unparseable LLM response", "raw_response": raw},
            )

        clamped_score = max(1, min(5, raw_score))
        normalized = round(clamped_score / 5.0, 4)

        return GraderResult(
            dimension=ScoreDimension.PROCESS,
            score=normalized,
            details={
                "raw_score": clamped_score,
                "reasoning": reasoning,
                "model": self.model,
            },
        )
