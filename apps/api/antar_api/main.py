"""FastAPI application factory.

Run with: ``uv run uvicorn antar_api.main:app --reload`` (or ``uv run antar serve``).
"""

import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from antar import __version__
from antar.backends.amd_cloud.cost import CloudSessionStore
from antar.backends.amd_cloud.ssh import RemoteRunner
from antar.backends.base import RuntimeBackend
from antar.backends.registry import build_backends, build_remote_runner
from antar.benchmarking.manager import BenchmarkManager, JobSlot
from antar.benchmarking.store import BenchmarkStore
from antar.comparison.manager import ComparisonManager
from antar.comparison.store import ComparisonStore
from antar.config.settings import Settings, get_settings
from antar.core.errors import AntarError
from antar.inference.service import InferenceService
from antar.inference.types import MAX_IMAGES_PER_REQUEST
from antar_api import (
    routes,
    routes_benchmarks,
    routes_cloud,
    routes_comparisons,
    routes_inference,
)
from antar_api.errors import GENERIC_MESSAGE, STATUS_BY_ERROR

logger = logging.getLogger(__name__)

# JSON overhead allowed on top of the base64 images a request may carry.
_BODY_OVERHEAD_BYTES = 2 * 1024 * 1024


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    manager: BenchmarkManager = app.state.benchmarks
    if manager.cancel():
        await manager.wait()
    comparisons: ComparisonManager = app.state.comparisons
    if comparisons.cancel("The Antar API shut down."):
        await comparisons.wait()


def create_app(
    settings: Settings | None = None,
    backends: Sequence[RuntimeBackend] | None = None,
    remote_runner: RemoteRunner | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    app = FastAPI(
        title="Antar API",
        version=__version__,
        description="Multimodal AI optimization, benchmarking, and cloud-to-edge deployment.",
        lifespan=_lifespan,
    )
    runtime = tuple(backends) if backends is not None else build_backends(resolved)
    store = BenchmarkStore(resolved.storage.benchmarks_dir)
    app.state.settings = resolved
    app.state.backends = runtime
    app.state.inference = InferenceService(runtime, max_image_bytes=resolved.max_image_bytes)
    app.state.benchmark_store = store
    slot = JobSlot()
    benchmarks = BenchmarkManager(runtime, store, slot)
    app.state.benchmarks = benchmarks
    sessions = CloudSessionStore(resolved.storage.cloud_dir, resolved.cloud_cost)
    comparison_store = ComparisonStore(resolved.storage.comparisons_dir)
    profile = resolved.amd_cloud
    app.state.cloud_sessions = sessions
    app.state.remote_runner = remote_runner or build_remote_runner(resolved)
    app.state.comparison_store = comparison_store
    app.state.comparisons = ComparisonManager(
        runtime,
        benchmarks,
        comparison_store,
        slot,
        cost=resolved.cloud_cost,
        session=sessions.load,
        vllm_image=resolved.cloud.vllm_image if resolved.cloud else None,
        gpu_interval_seconds=profile.gpu_poll_interval_seconds if profile else 10.0,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_origins),
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    # Base64 is 4/3 the size of the image it carries.
    max_body_bytes = (
        resolved.max_image_bytes * MAX_IMAGES_PER_REQUEST * 4 // 3 + _BODY_OVERHEAD_BYTES
    )

    @app.middleware("http")
    async def reject_oversized_bodies(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_body_bytes:
            return JSONResponse(status_code=413, content={"detail": "The request is too large."})
        return await call_next(request)

    @app.exception_handler(AntarError)
    async def handle_antar_error(_: Request, exc: AntarError) -> JSONResponse:
        status = STATUS_BY_ERROR.get(type(exc))
        if status is not None:
            return JSONResponse(status_code=status, content={"detail": str(exc)})
        # Anything else may include local paths; keep it in the server log only.
        logger.error("Request failed: %s", exc)
        return JSONResponse(status_code=500, content={"detail": GENERIC_MESSAGE})

    app.include_router(routes.health_router)
    app.include_router(routes_inference.router)
    app.include_router(routes.router)
    app.include_router(routes_benchmarks.router)
    app.include_router(routes_cloud.router)
    app.include_router(routes_comparisons.router)
    return app


app = create_app()
