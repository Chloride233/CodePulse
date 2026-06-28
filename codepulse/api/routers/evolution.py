"""Evolution endpoint — SkillOpt evolution results."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from codepulse.api.deps import get_results_dir
from codepulse.api.schemas import EvolutionEpochResponse, EvolutionResponse

if TYPE_CHECKING:
    from pathlib import Path

router = APIRouter(prefix="/api", tags=["evolution"])


@router.get("/evolution", response_model=EvolutionResponse)
def get_evolution(
    results_dir: Path = Depends(get_results_dir),
) -> EvolutionResponse:
    """Get evolution results from the results directory.

    Looks for evolution.json files that contain epoch-by-epoch results.
    Falls back to computing from trial data if no dedicated file exists.
    """
    base = results_dir

    # Try to load dedicated evolution results file
    evo_path = base / "evolution.json"
    if evo_path.exists():
        try:
            data = json.loads(evo_path.read_text(encoding="utf-8"))
            epochs = [
                EvolutionEpochResponse(**epoch)
                for epoch in data.get("epochs", [])
            ]
            return EvolutionResponse(epochs=epochs)
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    # Fallback: empty evolution (no data yet)
    return EvolutionResponse(epochs=[])
