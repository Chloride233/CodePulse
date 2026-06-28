"""CodePulse API — FastAPI application.

Serves the evaluation dashboard backend. Reads results from a configurable
``results/`` directory and exposes them via REST endpoints.

The results directory can be set via the ``CODEPULSE_RESULTS_DIR``
environment variable or by calling :func:`create_app` with a custom path.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from codepulse.api.routers import compare, evaluations, evolution, overview, traces

if TYPE_CHECKING:
    from pathlib import Path

_DEFAULT_RESULTS_DIR = "results"


def create_app(results_dir: str | Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        results_dir: Path to the directory containing evaluation results.
            Falls back to the ``CODEPULSE_RESULTS_DIR`` environment variable,
            then to ``"results"``.

    Returns:
        A fully configured FastAPI instance.
    """
    resolved = str(
        results_dir
        or os.environ.get("CODEPULSE_RESULTS_DIR")
        or _DEFAULT_RESULTS_DIR
    )

    application = FastAPI(
        title="CodePulse API",
        description="Code Agent evaluation and self-evolution framework — REST API",
        version="0.1.0",
    )

    # Store the results directory on app state so routers can access it.
    application.state.results_dir = resolved

    # CORS — allow Vue dev server
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    application.include_router(overview.router)
    application.include_router(evaluations.router)
    application.include_router(compare.router)
    application.include_router(traces.router)
    application.include_router(evolution.router)

    @application.get("/api/health")
    def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok", "version": "0.1.0"}

    return application


# Module-level default app for ``uvicorn codepulse.api.main:app``.
app = create_app()
