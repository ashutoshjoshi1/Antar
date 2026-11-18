"""Opt-in checks against a real vLLM endpoint on an AMD GPU host.

Never run by default or in CI. They use whatever is configured in the
environment (``ANTAR_CLOUD__BASE_URL``, and optionally ``amd_cloud`` for SSH):

    uv run pytest -m amd_live -s

They send a handful of short requests to a server that is already running, so
they cost only the instance time they take. They start and stop nothing.
"""

import asyncio

import pytest

from antar.backends.amd_cloud.backend import AmdCloudBackend
from antar.backends.base import Availability
from antar.backends.registry import build_cloud_backend
from antar.benchmarking.workloads import load_image
from antar.config.settings import Settings
from antar.core.types import Modality
from antar.inference.types import (
    ChatDelta,
    ChatDone,
    ChatMessage,
    ChatRequest,
    GenerationSettings,
)
from antar.models.spec import ModelSpec

pytestmark = pytest.mark.amd_live


@pytest.fixture(scope="module")
def backend() -> AmdCloudBackend:
    settings = Settings()
    if settings.cloud is None:
        pytest.skip("ANTAR_CLOUD__BASE_URL is not set")
    cloud = build_cloud_backend(settings)
    status = asyncio.run(cloud.status())
    if status.availability is not Availability.AVAILABLE:
        pytest.skip(f"cloud endpoint is not available: {status.detail}")
    return cloud


def _served(backend: AmdCloudBackend, modality: Modality | None = None) -> ModelSpec:
    models = [model for model in asyncio.run(backend.list_models()) if model.loaded]
    if modality is not None:
        models = [model for model in models if modality in model.modalities]
    if not models:
        pytest.skip(f"the endpoint serves no {modality.value if modality else ''} model")
    return models[0]


def _ask(model: ModelSpec, text: str, image: str | None = None) -> ChatRequest:
    images = (load_image(image),) if image else ()
    return ChatRequest(
        model=model.id,
        messages=(ChatMessage(role="user", content=text, images=images),),
        settings=GenerationSettings(max_tokens=64, temperature=0, enable_thinking=False),
    )


def test_live_server_reports_version_and_a_served_model(backend: AmdCloudBackend) -> None:
    status = asyncio.run(backend.status())

    assert status.version
    assert _served(backend).context_length


def test_live_text_chat_returns_tokens_and_usage(backend: AmdCloudBackend) -> None:
    result = asyncio.run(backend.chat(_ask(_served(backend), "Reply with the single word: ready")))

    assert result.content.strip()
    assert result.metrics.completion_tokens
    assert result.metrics.prompt_tokens


def test_live_streaming_delivers_deltas_then_a_result(backend: AmdCloudBackend) -> None:
    async def collect() -> list[object]:
        request = _ask(_served(backend), "Count from 1 to 5.")
        return [event async for event in backend.chat_stream(request)]

    events = asyncio.run(collect())

    assert any(isinstance(event, ChatDelta) for event in events)
    (done,) = [event for event in events if isinstance(event, ChatDone)]
    assert done.result.metrics.first_chunk_ms is not None
    assert done.result.metrics.completion_tokens


def test_live_thinking_can_be_switched_off(backend: AmdCloudBackend) -> None:
    result = asyncio.run(backend.chat(_ask(_served(backend), "What is 2 + 2?")))

    # Confirms that chat_template_kwargs reaches the server; see antar/backends/amd_cloud/vllm.py.
    assert not result.reasoning
    assert "<think>" not in result.content


def test_live_vision_reads_a_bundled_image(backend: AmdCloudBackend) -> None:
    model = _served(backend, Modality.VISION)

    result = asyncio.run(
        backend.chat(_ask(model, "What colour is the square? One word.", "shapes.png"))
    )

    assert "blue" in result.content.lower()


def test_live_gpu_readings_name_an_amd_device(backend: AmdCloudBackend) -> None:
    sample = asyncio.run(backend.gpu_sample())
    if sample is None:
        pytest.skip("no SSH host configured (amd_cloud)")

    # If this fails, amd-smi's JSON keys differ from what antar/backends/amd_cloud/amd_smi.py
    # reads. Capture `amd-smi static --json` and `amd-smi metric --json` and fix the parser.
    assert sample.gpus, sample.unavailable
    assert all(gpu.name and gpu.memory_total_bytes for gpu in sample.gpus), sample.unavailable
