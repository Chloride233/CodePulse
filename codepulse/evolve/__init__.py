"""Layer 5: 自进化层 — SkillOpt 训练循环。

Forward → Backward → Validate → Buffer，四类样本归因，经验三级进化。
还包括 SuggestionEngine 用于基于评测分数的优化建议生成。
"""

from codepulse.evolve.attribution import AttributionReport, SampleAttribution
from codepulse.evolve.buffer import EditBuffer
from codepulse.evolve.experience import ExperienceEvolution, Instinct, Lesson, Pattern
from codepulse.evolve.forward import ForwardPass, Trajectory
from codepulse.evolve.gate import ValidationGate
from codepulse.evolve.prompt_edit import EditBatch, EditType, PromptEdit, RejectedEdit
from codepulse.evolve.scheduler import (
    AdaptiveScheduler,
    CombinedScheduler,
    CosineDecayScheduler,
    Scheduler,
)
from codepulse.evolve.skillopt import EvolutionResult, SkillOpt
from codepulse.evolve.suggest import Suggestion, SuggestionEngine, SuggestionPriority

__all__ = [
    "AdaptiveScheduler",
    "AttributionReport",
    "CombinedScheduler",
    "CosineDecayScheduler",
    "EditBatch",
    "EditBuffer",
    "EditType",
    "EvolutionResult",
    "ExperienceEvolution",
    "ForwardPass",
    "Instinct",
    "Lesson",
    "Pattern",
    "PromptEdit",
    "RejectedEdit",
    "SampleAttribution",
    "Scheduler",
    "SkillOpt",
    "Suggestion",
    "SuggestionEngine",
    "SuggestionPriority",
    "Trajectory",
    "ValidationGate",
]
