"""Model management, inference, and telemetry routes.

All backend traffic originates here on the server. The browser never talks to
Lemonade, and requests name a configured backend rather than a URL.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from antar.backends.base import Availability, DownloadJob, RuntimeBackend
from antar.backends.lemonade.backend import LemonadeBackend
from antar.benchmarking.manager import BenchmarkManager
from antar.core.errors import (
    AntarError,
    BackendUnavailableError,
    BenchmarkBusyError,
    ModelNotFoundError,
)
from antar.hardware.telemetry import collect_telemetry
from antar.inference.service import InferenceService, get_backend
from antar.inference.types import ChatEvent, ChatResult
from antar.models.spec import ModelSpec
from antar_api.errors import public_message
from antar_api.routes import BackendsDep
from antar_api.schemas import (
    ChatBody,
    DownloadBody,
    DownloadsResponse,
    ErrorEvent,
    LoadedModel,
    ModelActionBody,
    TelemetryResponse,
)

logger = logging.getLogger(__name__)


def get_inference(request: Request) -> InferenceService:
    service: InferenceService = request.app.state.inference
    return service


def get_benchmarks(request: Request) -> BenchmarkManager:
    manager: BenchmarkManager = request.app.state.benchmarks
    return manager


InferenceDep = Annotated[InferenceService, Depends(get_inference)]
BenchmarksDep = Annotated[BenchmarkManager, Depends(get_benchmarks)]


def require_idle(manager: BenchmarksDep) -> None:
    """Keep other work off the backend while a benchmark is measuring it."""
    if manager.is_running:
        raise BenchmarkBusyError(
            "A benchmark or comparison is running. Wait for it to finish, or cancel it."
        )


IDLE = [Depends(require_idle)]

router = APIRouter(prefix="/api/v1")


@router.get("/models/downloads", tags=["models"])
async def downloads(backends: BackendsDep) -> DownloadsResponse:
    """Downloads in progress on any reachable backend."""
    jobs: list[DownloadJob] = []
    for backend in backends:
        try:
            jobs.extend(await backend.downloads())
        except BackendUnavailableError:
            continue
    return DownloadsResponse(downloads=tuple(jobs))


@router.get("/models/{backend}/{model_id:path}", tags=["models"])
async def model_details(backend: str, model_id: str, backends: BackendsDep) -> ModelSpec:
    models = await get_backend(backends, backend).list_models()
    spec = next((model for model in models if model.id == model_id), None)
    if spec is None:
        raise ModelNotFoundError(f"Backend '{backend}' has no model named '{model_id}'.")
    return spec


@router.post("/models/load", tags=["models"], dependencies=IDLE)
async def load_model(body: ModelActionBody, backends: BackendsDep) -> ModelSpec:
    """Load a model that is already downloaded. Never triggers a download."""
    await get_backend(backends, body.backend).load_model(body.model)
    return await model_details(body.backend, body.model, backends)


@router.post("/models/unload", tags=["models"], dependencies=IDLE)
async def unload_model(body: ModelActionBody, backends: BackendsDep) -> ModelSpec:
    await get_backend(backends, body.backend).unload_model(body.model)
    return await model_details(body.backend, body.model, backends)


@router.post("/models/download", tags=["models"], status_code=202)
async def download_model(body: DownloadBody, backends: BackendsDep) -> DownloadsResponse:
    """Start a download. Requires ``confirm: true``; Antar never downloads on its own."""
    backend = get_backend(backends, body.backend)
    await backend.download_model(body.model)
    return DownloadsResponse(downloads=await backend.downloads())


@router.post("/inference/chat", tags=["inference"], dependencies=IDLE)
async def chat(body: ChatBody, service: InferenceDep) -> ChatResult:
    """Text or image-understanding chat, returned once generation finishes."""
    return await service.chat(body.backend, body)


async def _sse(stream: AsyncIterator[ChatEvent]) -> AsyncIterator[str]:
    """Serialize events as Server-Sent Events.

    If the client disconnects, Starlette cancels this generator; closing the
    backend stream in ``finally`` is what stops generation downstream.
    """
    try:
        async for event in stream:
            yield f"data: {event.model_dump_json()}\n\n"
    except AntarError as exc:
        logger.warning("Streaming chat failed: %s", exc)
        payload = ErrorEvent(message=public_message(exc), kind=type(exc).__name__)
        yield f"data: {payload.model_dump_json()}\n\n"
    finally:
        close = getattr(stream, "aclose", None)
        if close is not None:
            await close()


@router.post("/inference/chat/stream", tags=["inference"], dependencies=IDLE)
async def chat_stream(body: ChatBody, service: InferenceDep) -> StreamingResponse:
    """Streaming chat as Server-Sent Events: ``delta`` events, then ``done`` or ``error``."""
    stream = service.chat_stream(body.backend, body)
    return StreamingResponse(
        _sse(stream),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _loaded(backend: RuntimeBackend) -> tuple[tuple[str, int | None], ...]:
    try:
        return await backend.model_processes()
    except AntarError:
        return ()


@router.get("/telemetry", tags=["hardware"])
async def telemetry(backends: BackendsDep, manager: BenchmarksDep) -> TelemetryResponse:
    per_backend = await asyncio.gather(*(_loaded(backend) for backend in backends))
    processes = tuple(process for group in per_backend for process in group)
    stats = None
    for backend in backends:
        if isinstance(backend, LemonadeBackend):
            status = await backend.status()
            if status.availability is Availability.AVAILABLE:
                try:
                    stats = await backend.stats()
                except AntarError:
                    stats = None
    return TelemetryResponse(
        system=await run_in_threadpool(collect_telemetry, processes),
        loaded_models=tuple(
            LoadedModel(backend=backend.name, model=model)
            for backend, group in zip(backends, per_backend, strict=True)
            for model, _ in group
        ),
        lemonade_stats=stats,
        benchmark_running=manager.is_running,
    )
