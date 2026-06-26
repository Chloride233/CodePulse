"""Layer 5: 自进化层 — SkillOpt 训练循环。

Forward → Backward → Validate → Buffer，四类样本归因，经验三级进化。
"""

from codepulse.evolve.attribution import AttributionReport, SampleAttribution
from codepulse.evolve.prompt_edit import EditBatch, EditType, PromptEdit, RejectedEdit

__all__ = [
    "AttributionReport",
    "EditBatch",
    "EditType",
    "PromptEdit",
    "RejectedEdit",
    "SampleAttribution",
]
