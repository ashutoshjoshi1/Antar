"""FastAPI application factory.

Run with: ``uv run uvicorn antar_api.main:app --reload`` (or ``uv run antar serve``).
"""

import logging
from collections.abc import Sequence

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from antar import __version__
from antar.backends.base import RuntimeBackend
from antar.backends.registry import build_backends
from antar.config.settings import Settings, get_settings
from antar.core.errors import AntarError
from antar_api.routes import health_router, router

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None, backends: Sequence[RuntimeBackend] | None = None
) -> FastAPI:
    resolved = settings or get_settings()
    app = FastAPI(
        title="Antar API",
        version=__version__,
        description="Multimodal AI optimization, benchmarking, and cloud-to-edge deployment.",
    )
    app.state.settings = resolved
    app.state.backends = tuple(backends) if backends is not None else build_backends(resolved)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_origins),
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.exception_handler(AntarError)
    async def handle_antar_error(_: Request, exc: AntarError) -> JSONResponse:
        # Details may include local paths; keep them in the server log only.
        logger.error("Request failed: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "The request failed. See the Antar API log for details."},
        )

    app.include_router(health_router)
    app.include_router(router)
    return app


app = create_app()
