import asyncio

import httpx
import pytest

from antar.backends.base import Availability, SupportLevel
from antar.backends.lemonade.backend import LemonadeBackend, to_model_spec
from antar.backends.lemonade.client import LemonadeClient, LemonadeModel
from antar.core.errors import BackendUnavailableError
from antar.core.types import Modality, Task


def _backend(transport: httpx.MockTransport, api_key: str | None = None) -> LemonadeBackend:
    return LemonadeBackend(LemonadeClient(api_key=api_key, transport=transport))


def test_status_is_available_and_reports_version_when_server_is_healthy(
    lemonade_transport: httpx.MockTransport,
) -> None:
    status = asyncio.run(_backend(lemonade_transport).status())

    assert status.availability is Availability.AVAILABLE
    assert status.version == "2026.46.2"
    assert status.endpoint == "http://localhost:13305/v1"
    assert "Qwen3-0.6B-GGUF" in status.detail


def test_status_is_unavailable_with_guidance_when_server_is_not_running(
    offline_transport: httpx.MockTransport,
) -> None:
    status = asyncio.run(_backend(offline_transport).status())

    assert status.availability is Availability.UNAVAILABLE
    assert "Could not connect to Lemonade" in status.detail


def test_status_is_unavailable_when_request_times_out() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    status = asyncio.run(_backend(httpx.MockTransport(timeout)).status())

    assert status.availability is Availability.UNAVAILABLE
    assert "did not respond" in status.detail


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            httpx.Response(401, json={"error": "Invalid or missing API key"}),
            "ANTAR_LEMONADE__API_KEY",
        ),
        (httpx.Response(503), "HTTP 503"),
        (httpx.Response(200, text="<html>not lemonade</html>"), "did not return JSON"),
        (httpx.Response(200, json={"unexpected": True}), "Unexpected response"),
    ],
)
def test_status_explains_unusable_responses(response: httpx.Response, expected: str) -> None:
    status = asyncio.run(_backend(httpx.MockTransport(lambda _: response)).status())

    assert status.availability is Availability.UNAVAILABLE
    assert expected in status.detail


def test_api_key_is_sent_as_bearer_token() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"status": "ok"})

    asyncio.run(_backend(httpx.MockTransport(handler), api_key="secret").status())

    assert seen == ["Bearer secret"]


def test_list_models_requests_full_catalog_and_maps_labels(
    lemonade_transport: httpx.MockTransport,
) -> None:
    models = {model.id: model for model in asyncio.run(_backend(lemonade_transport).list_models())}

    vlm = models["Gemma-3-4b-it-GGUF"]
    assert set(vlm.modalities) == {Modality.TEXT, Modality.VISION}
    assert vlm.downloaded is False
    assert vlm.size_bytes is None
    assert vlm.labels == ("chat", "vision", "hot")

    whisper = models["Whisper-Tiny"]
    assert whisper.modalities == (Modality.SPEECH,)
    assert whisper.tasks == (Task.SPEECH_TO_TEXT,)
    assert whisper.size_bytes == 75_000_000


def test_list_models_passes_show_all() -> None:
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        queries.append(request.url.query.decode())
        return httpx.Response(200, json={"object": "list", "data": []})

    asyncio.run(_backend(httpx.MockTransport(handler)).list_models())

    assert queries == ["show_all=true"]


def test_list_models_skips_malformed_entries_and_keeps_the_rest() -> None:
    payload = {"data": [{"id": ""}, {"no_id": True}, {"id": "Good-Model", "labels": ["chat"]}]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))

    models = asyncio.run(_backend(transport).list_models())

    assert [model.id for model in models] == ["Good-Model"]


def test_llamacpp_model_without_deployment_label_defaults_to_chat() -> None:
    spec = to_model_spec(LemonadeModel(id="m", recipe="llamacpp", labels=("reasoning",)))

    assert spec.modalities == (Modality.TEXT,)
    assert spec.tasks == (Task.CHAT,)


def test_model_with_unknown_recipe_and_labels_is_left_unclassified() -> None:
    spec = to_model_spec(LemonadeModel(id="m", recipe="new-recipe", labels=("mesh-thing",)))

    assert spec.modalities == ()
    assert spec.labels == ("mesh-thing",)


def test_list_models_raises_when_server_is_unreachable(
    offline_transport: httpx.MockTransport,
) -> None:
    with pytest.raises(BackendUnavailableError):
        asyncio.run(_backend(offline_transport).list_models())


def test_capabilities_never_claim_antar_support_and_exclude_video(
    lemonade_transport: httpx.MockTransport,
) -> None:
    capabilities = _backend(lemonade_transport).capabilities()

    assert all(capability.support is not SupportLevel.SUPPORTED for capability in capabilities)
    video = [capability for capability in capabilities if capability.modality is Modality.VIDEO]
    assert [capability.support for capability in video] == [SupportLevel.UNSUPPORTED]
