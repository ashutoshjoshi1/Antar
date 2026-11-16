"""Live tests against a real Lemonade server. Opt-in:

    uv run pytest -m lemonade_live

They are skipped unless Lemonade is reachable and already has a suitable model
downloaded. They never download anything.
"""

import asyncio

import pytest

from antar.backends.base import Availability
from antar.backends.lemonade.backend import LemonadeBackend
from antar.backends.lemonade.client import LemonadeClient
from antar.benchmarking.workloads import load_image
from antar.config.settings import get_settings
from antar.core.types import Modality
from antar.inference.types import ChatDone, ChatMessage, ChatRequest, GenerationSettings
from antar.models.spec import ModelSpec

pytestmark = pytest.mark.lemonade_live


def _backend() -> LemonadeBackend:
    lemonade = get_settings().lemonade
    key = lemonade.api_key.get_secret_value() if lemonade.api_key else None
    return LemonadeBackend(LemonadeClient(str(lemonade.base_url), api_key=key))


def _downloaded(modality: Modality) -> ModelSpec:
    backend = _backend()
    if asyncio.run(backend.status()).availability is not Availability.AVAILABLE:
        pytest.skip("Lemonade is not reachable")
    candidates = [
        model
        for model in asyncio.run(backend.list_models())
        if model.downloaded and modality in model.modalities and "chat" in model.labels
    ]
    if not candidates:
        pytest.skip(f"No downloaded {modality.value} chat model in Lemonade")
    # Prefer one that is already loaded, then the smallest, to keep the test quick.
    return min(candidates, key=lambda model: (not model.loaded, model.size_bytes or 0))


def _request(model: ModelSpec, message: ChatMessage, max_tokens: int = 64) -> ChatRequest:
    settings = GenerationSettings(max_tokens=max_tokens, temperature=0, enable_thinking=False)
    return ChatRequest(model=model.id, messages=(message,), settings=settings)


def test_live_text_chat_returns_text_and_backend_timings() -> None:
    model = _downloaded(Modality.TEXT)
    message = ChatMessage(role="user", content="Reply with the single word: ready")

    result = asyncio.run(_backend().chat(_request(model, message)))

    assert result.content.strip()
    assert result.simulated is False
    assert result.metrics.completion_tokens
    assert result.metrics.tokens_per_second


def test_live_streaming_delivers_incremental_deltas() -> None:
    model = _downloaded(Modality.TEXT)
    message = ChatMessage(role="user", content="Count from one to five in words.")

    async def collect() -> tuple[int, ChatDone]:
        deltas, done = 0, None
        async for event in _backend().chat_stream(_request(model, message)):
            if isinstance(event, ChatDone):
                done = event
            else:
                deltas += 1
        assert done is not None
        return deltas, done

    deltas, done = asyncio.run(collect())

    assert deltas > 1
    assert done.result.content.strip()
    assert done.result.metrics.first_chunk_ms is not None


def test_live_cancelled_stream_stops_generation_on_the_server() -> None:
    model = _downloaded(Modality.TEXT)
    message = ChatMessage(role="user", content="Write a very long story about a lighthouse.")
    backend = _backend()

    async def scenario() -> int:
        stream = backend.chat_stream(_request(model, message, max_tokens=4000))
        async for _ in stream:
            break
        await stream.aclose()
        await asyncio.sleep(1.0)
        live = (await backend.stats()).live
        assert live is not None
        assert live.active_requests is not None
        return live.active_requests

    assert asyncio.run(scenario()) == 0


def test_live_vision_model_describes_a_bundled_image() -> None:
    model = _downloaded(Modality.VISION)
    message = ChatMessage(
        role="user",
        content="What colors are the shapes in this image?",
        images=(load_image("shapes.png"),),
    )

    result = asyncio.run(_backend().chat(_request(model, message, max_tokens=120)))

    # Only that the model answered: correctness is judged by a person, not asserted here.
    assert result.content.strip()
    assert result.metrics.completion_tokens
