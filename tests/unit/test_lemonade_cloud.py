"""Models Lemonade relays to a registered cloud provider, and the calls that register one."""

import asyncio

import httpx
import pytest

from antar.backends.lemonade.backend import LemonadeBackend
from antar.backends.lemonade.client import LemonadeClient
from antar.core.errors import CapabilityNotSupportedError
from antar.core.types import Modality
from antar.inference.types import ChatMessage, ChatRequest, ImageInput
from antar.models.spec import ExecutionLocation, ModelState
from tests.conftest import LEMONADE_MODELS, FakeLemonade

# The entry Lemonade 2026.46.2 produced for a model discovered on a registered provider.
CLOUD_MODEL = {
    "id": "antaramd.Qwen/Qwen3-8B",
    "checkpoint": "Qwen/Qwen3-8B",
    "cloud_provider": "antaramd",
    "downloaded": True,
    "labels": ["cloud", "chat"],
    "recipe": "cloud",
}
IMAGE = ImageInput(media_type="image/png", data_base64="iVBORw0KGgo=")


def _backend(fake: FakeLemonade) -> LemonadeBackend:
    models = {**LEMONADE_MODELS, "data": [*LEMONADE_MODELS["data"], CLOUD_MODEL]}
    fake.overrides[("GET", "/v1/models")] = httpx.Response(200, json=models)
    return LemonadeBackend(LemonadeClient(transport=httpx.MockTransport(fake)))


def test_a_lemonade_cloud_model_is_marked_as_running_in_the_cloud(
    fake_lemonade: FakeLemonade,
) -> None:
    models = {model.id: model for model in asyncio.run(_backend(fake_lemonade).list_models())}

    cloud = models["antaramd.Qwen/Qwen3-8B"]
    assert cloud.backend == "lemonade"
    assert cloud.location is ExecutionLocation.CLOUD
    assert cloud.provider == "antaramd"
    assert cloud.state is ModelState.LOADED
    assert cloud.modalities == (Modality.TEXT,)
    assert models["Qwen3-0.6B-GGUF"].location is ExecutionLocation.LOCAL
    assert models["Qwen3-0.6B-GGUF"].provider == "lemonade"


def test_a_lemonade_cloud_model_is_relayed_through_the_same_chat_path(
    fake_lemonade: FakeLemonade,
) -> None:
    request = ChatRequest(
        model="antaramd.Qwen/Qwen3-8B", messages=(ChatMessage(role="user", content="hi"),)
    )

    result = asyncio.run(_backend(fake_lemonade).chat(request))

    assert result.backend == "lemonade"
    assert fake_lemonade.posts("/v1/chat/completions")[0]["model"] == "antaramd.Qwen/Qwen3-8B"


def test_lemonade_refuses_several_images_in_one_message(fake_lemonade: FakeLemonade) -> None:
    message = ChatMessage(role="user", content="compare", images=(IMAGE, IMAGE))
    request = ChatRequest(model="Tiny-VLM-GGUF", messages=(message,))

    with pytest.raises(CapabilityNotSupportedError, match="one image per message"):
        asyncio.run(_backend(fake_lemonade).chat(request))

    assert fake_lemonade.posts("/v1/chat/completions") == []


def test_registering_a_provider_fails_clearly_when_lemonade_did_not_keep_it(
    fake_lemonade: FakeLemonade,
) -> None:
    empty = httpx.Response(200, json={"cloud": {"providers": []}})
    fake_lemonade.overrides[("GET", "/v1/system-info")] = empty
    fake_lemonade.overrides[("POST", "/v1/install")] = httpx.Response(200, json={})
    backend = _backend(fake_lemonade)

    with pytest.raises(Exception, match="did not keep the provider"):
        asyncio.run(backend.register_cloud_provider("antaramd", "https://gpu.example/v1", None))

    # No key was supplied, so none is sent, and an https URL needs no plaintext opt-in.
    assert fake_lemonade.posts("/v1/cloud/auth") == []
