"""Layer 5: 自进化层 — SkillOpt 训练循环。

Forward → Backward → Validate → Buffer，四类样本归因，经验三级进化。
"""

from codepulse.evolve.attribution import AttributionReport, SampleAttribution
from codepulse.evolve.buffer import EditBuffer
from codepulse.evolve.forward import ForwardPass, Trajectory
from codepulse.evolve.gate import ValidationGate
from codepulse.evolve.prompt_edit import EditBatch, EditType, PromptEdit, RejectedEdit
from codepulse.evolve.skillopt import EvolutionResult, SkillOpt

__all__ = [
    "AttributionReport",
    "EditBatch",
    "EditBuffer",
    "EditType",
    "EvolutionResult",
    "ForwardPass",
    "PromptEdit",
    "RejectedEdit",
    "SampleAttribution",
    "SkillOpt",
    "Trajectory",
    "ValidationGate",
]
