"""The AMD cloud backend against a stand-in vLLM server. No network, no GPU, no SSH."""

import asyncio
import base64
import json
from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from antar.backends.amd_cloud.backend import AmdCloudBackend
from antar.backends.amd_cloud.config import (
    AmdCloudProfile,
    CloudEndpointSettings,
    CloudModelConfig,
)
from antar.backends.amd_cloud.ssh import ssh_arguments
from antar.backends.amd_cloud.vllm import VllmClient, build_chat_payload
from antar.backends.base import Availability
from antar.core.errors import (
    BackendRequestError,
    BackendUnavailableError,
    CapabilityNotSupportedError,
    ModelNotFoundError,
)
from antar.core.types import Modality
from antar.inference.types import (
    ChatDelta,
    ChatDone,
    ChatMessage,
    ChatRequest,
    GenerationSettings,
    ImageInput,
)
from antar.models.spec import ExecutionLocation, ModelState
from tests.conftest import CLOUD_URL, VLLM_KEY, FakeVllm, refuse_connection

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 16).decode()
IMAGE = ImageInput(media_type="image/png", data_base64=PNG)
TEXT_MODEL = "Qwen/Qwen3-8B"
VISION_MODEL = "Qwen/Qwen3-VL-8B-Instruct"


def _backend(
    handler: httpx.MockTransport | FakeVllm,
    *,
    key: str | None = None,
    models: tuple[CloudModelConfig, ...] = (),
    generation_timeout: float = 600.0,
) -> AmdCloudBackend:
    transport = (
        handler if isinstance(handler, httpx.MockTransport) else httpx.MockTransport(handler)
    )
    endpoint = CloudEndpointSettings.model_validate({"base_url": CLOUD_URL, "models": models})
    client = VllmClient(
        CLOUD_URL, api_key=key, generation_timeout_seconds=generation_timeout, transport=transport
    )
    return AmdCloudBackend(endpoint=endpoint, client=client)


def _request(model: str = TEXT_MODEL, images: int = 0, **settings: object) -> ChatRequest:
    message = ChatMessage(role="user", content="What is 6 x 7?", images=(IMAGE,) * images)
    return ChatRequest(
        model=model, messages=(message,), settings=GenerationSettings.model_validate(settings)
    )


# --- configuration: which destinations are allowed -------------------------------------


@pytest.mark.parametrize("url", ["http://127.0.0.1:18000/v1", "http://localhost:18000/v1"])
def test_a_loopback_endpoint_is_trusted_without_a_key(url: str) -> None:
    assert CloudEndpointSettings.model_validate({"base_url": url}).api_key is None


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"base_url": "http://gpu.example.com:8000/v1"}, "not a loopback address"),
        (
            {"base_url": "http://gpu.example.com/v1", "trusted_hosts": ["gpu.example.com"]},
            "must use https",
        ),
        (
            {"base_url": "https://gpu.example.com/v1", "trusted_hosts": ["gpu.example.com"]},
            "must have an api_key",
        ),
        ({"base_url": "http://user:pw@127.0.0.1:18000/v1"}, "must not contain credentials"),
    ],
)
def test_untrusted_or_unsafe_endpoints_are_rejected(
    values: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        CloudEndpointSettings.model_validate(values)


def test_a_remote_endpoint_needs_the_allowlist_https_and_a_key() -> None:
    endpoint = CloudEndpointSettings.model_validate(
        {
            "base_url": "https://gpu.example.com/v1",
            "trusted_hosts": ["gpu.example.com"],
            "api_key": SecretStr("k"),
        }
    )

    assert endpoint.base_url.host == "gpu.example.com"


def test_ssh_arguments_never_prompt_and_cannot_be_read_as_options() -> None:
    profile = AmdCloudProfile(name="lab", ssh_host="amd-box", ssh_port=2222)

    arguments = ssh_arguments(profile)

    assert arguments[-2:] == ["--", "amd-box"]
    assert "BatchMode=yes" in arguments
    assert arguments[arguments.index("-p") + 1] == "2222"
    with_user = AmdCloudProfile(name="lab", ssh_host="10.0.0.5", ssh_user="ubuntu")
    assert ssh_arguments(with_user)[-1] == "ubuntu@10.0.0.5"


# --- connection status -----------------------------------------------------------------


def test_status_reports_the_served_model_and_version(fake_vllm: FakeVllm) -> None:
    status = asyncio.run(_backend(fake_vllm).status())

    assert status.availability is Availability.AVAILABLE
    assert status.version == "0.34.0"
    assert TEXT_MODEL in status.detail
    assert status.endpoint == CLOUD_URL


def test_an_unreachable_endpoint_is_a_status_not_a_crash() -> None:
    backend = _backend(httpx.MockTransport(refuse_connection))

    status = asyncio.run(backend.status())

    assert status.availability is Availability.UNAVAILABLE
    assert "SSH tunnel" in status.detail
    with pytest.raises(BackendUnavailableError):
        asyncio.run(backend.chat(_request()))


def test_a_loading_server_is_reported_as_loading(fake_vllm: FakeVllm) -> None:
    fake_vllm.health_status = 503

    status = asyncio.run(_backend(fake_vllm).status())

    assert status.availability is Availability.UNAVAILABLE
    assert "still loading" in status.detail


def test_a_wrong_api_key_names_the_setting_to_fix() -> None:
    server = FakeVllm(key=VLLM_KEY)

    wrong = asyncio.run(_backend(server, key="nope").status())
    right = asyncio.run(_backend(server, key=VLLM_KEY).status())

    assert wrong.availability is Availability.UNAVAILABLE
    assert "ANTAR_CLOUD__API_KEY" in wrong.detail
    assert right.availability is Availability.AVAILABLE


# --- model discovery -------------------------------------------------------------------


def test_served_models_are_described_from_the_verified_catalog(fake_vllm: FakeVllm) -> None:
    (spec,) = asyncio.run(_backend(fake_vllm).list_models())

    assert spec.location is ExecutionLocation.CLOUD
    assert spec.state is ModelState.LOADED
    assert spec.provider == "vllm"
    assert spec.modalities == (Modality.TEXT,)
    assert spec.parameter_count == 8_190_735_360
    assert spec.quantization == "BF16"
    assert spec.license == "apache-2.0"
    # The context the server was started with, not the model's theoretical maximum.
    assert spec.context_length == 32768


def test_an_unknown_served_model_is_left_unclassified_rather_than_guessed() -> None:
    (spec,) = asyncio.run(_backend(FakeVllm(models=("acme/mystery",))).list_models())

    assert spec.modalities == ()
    assert spec.parameter_count is None
    assert spec.size_bytes is None
    assert spec.loaded is True


def test_a_declared_model_that_is_not_served_is_listed_as_configured(fake_vllm: FakeVllm) -> None:
    declared = CloudModelConfig(id="my-vl", source=VISION_MODEL, modalities=("text", "vision"))

    models = {m.id: m for m in asyncio.run(_backend(fake_vllm, models=(declared,)).list_models())}

    assert models["my-vl"].state is ModelState.CONFIGURED
    assert models["my-vl"].loaded is False
    assert models["my-vl"].family == "Qwen3-VL"
    assert models[TEXT_MODEL].state is ModelState.LOADED


# --- inference -------------------------------------------------------------------------


def test_chat_returns_content_reasoning_and_only_what_was_measured(fake_vllm: FakeVllm) -> None:
    result = asyncio.run(_backend(fake_vllm).chat(_request(temperature=0.2, seed=7)))

    assert (result.content, result.reasoning, result.backend) == ("42", "Hm.", "amd_cloud")
    assert result.simulated is False
    assert (result.metrics.prompt_tokens, result.metrics.completion_tokens) == (11, 4)
    # vLLM reports no per-response timings, so these stay unavailable rather than invented.
    assert result.metrics.tokens_per_second is None
    assert result.metrics.prompt_processing_ms is None
    sent = fake_vllm.chats()[0]
    assert (sent["temperature"], sent["seed"], sent["stream"]) == (0.2, 7, False)


def test_thinking_is_switched_through_the_chat_template() -> None:
    off = build_chat_payload(_request(enable_thinking=False), stream=True)
    default = build_chat_payload(_request(), stream=False)

    assert off["chat_template_kwargs"] == {"enable_thinking": False}
    assert off["stream_options"] == {"include_usage": True}
    assert "chat_template_kwargs" not in default


def test_streaming_yields_deltas_then_one_result_with_first_chunk_time(fake_vllm: FakeVllm) -> None:
    async def collect() -> list[object]:
        return [event async for event in _backend(fake_vllm).chat_stream(_request())]

    events = asyncio.run(collect())

    assert [e.reasoning or e.content for e in events if isinstance(e, ChatDelta)] == ["Hm.", "42"]
    (done,) = [event for event in events if isinstance(event, ChatDone)]
    assert done.result.content == "42"
    assert done.result.reasoning == "Hm."
    assert done.result.metrics.first_chunk_ms is not None
    assert done.result.metrics.completion_tokens == 4


def test_a_model_that_is_not_served_is_refused_before_any_request(fake_vllm: FakeVllm) -> None:
    with pytest.raises(ModelNotFoundError, match=r"start_vllm\.sh"):
        asyncio.run(_backend(fake_vllm).chat(_request("Qwen/Qwen3-32B")))

    assert fake_vllm.chats() == []


def test_images_need_a_model_known_to_accept_them(fake_vllm: FakeVllm) -> None:
    with pytest.raises(CapabilityNotSupportedError, match="not known to accept images"):
        asyncio.run(_backend(fake_vllm).chat(_request(images=1)))

    assert fake_vllm.chats() == []


def test_a_vision_model_receives_every_image_as_a_data_url() -> None:
    server = FakeVllm(models=(VISION_MODEL,))

    asyncio.run(_backend(server).chat(_request(VISION_MODEL, images=2)))

    content = server.chats()[0]["messages"][0]["content"]  # type: ignore[index]
    kinds = [part["type"] for part in content]
    assert kinds == ["text", "image_url", "image_url"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_gpu_memory_exhaustion_is_named_as_such(fake_vllm: FakeVllm) -> None:
    error = {"error": {"message": "HIP out of memory. Tried to allocate 2.00 GiB"}}
    fake_vllm.overrides["/v1/chat/completions"] = httpx.Response(500, json=error)

    with pytest.raises(BackendRequestError, match="GPU memory exhausted"):
        asyncio.run(_backend(fake_vllm).chat(_request()))


def test_an_error_event_in_the_stream_fails_the_request(fake_vllm: FakeVllm) -> None:
    body = b'data: {"error": {"message": "context length exceeded"}}\n\n'
    fake_vllm.overrides["/v1/chat/completions"] = httpx.Response(200, content=body)

    async def collect() -> None:
        async for _ in _backend(fake_vllm).chat_stream(_request()):
            pass

    with pytest.raises(BackendRequestError, match="context length exceeded"):
        asyncio.run(collect())


def test_a_generation_timeout_is_reported_as_unavailable() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/completions":
            raise httpx.ReadTimeout("timed out", request=request)
        return FakeVllm()(request)

    backend = _backend(httpx.MockTransport(slow), generation_timeout=1.5)

    with pytest.raises(BackendUnavailableError, match=r"1\.5s"):
        asyncio.run(backend.chat(_request()))


def test_closing_the_stream_early_closes_the_connection() -> None:
    closed: list[bool] = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b'data: {"choices":[{"index":0,"delta":{"content":"a"}}]}\n\n'
            await asyncio.sleep(3600)

        async def aclose(self) -> None:
            closed.append(True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(200, stream=Stream())
        return FakeVllm()(request)

    async def cancel_after_first_token() -> None:
        stream = _backend(httpx.MockTransport(handler)).chat_stream(_request())
        assert isinstance(await anext(stream), ChatDelta)
        await stream.aclose()

    asyncio.run(cancel_after_first_token())

    assert closed == [True]


def test_requests_can_run_concurrently(fake_vllm: FakeVllm) -> None:
    backend = _backend(fake_vllm)

    async def many() -> list[str]:
        results = await asyncio.gather(*(backend.chat(_request()) for _ in range(8)))
        return [result.content for result in results]

    assert asyncio.run(many()) == ["42"] * 8
    assert len(fake_vllm.chats()) == 8


def test_load_only_confirms_the_served_model_and_unload_is_not_offered(fake_vllm: FakeVllm) -> None:
    backend = _backend(fake_vllm)

    asyncio.run(backend.load_model(TEXT_MODEL))
    with pytest.raises(CapabilityNotSupportedError):
        asyncio.run(backend.unload_model(TEXT_MODEL))
    with pytest.raises(CapabilityNotSupportedError):
        asyncio.run(backend.download_model(TEXT_MODEL))
    assert json.dumps(fake_vllm.requests).count("/v1/chat/completions") == 0


def test_error_text_from_the_server_never_carries_image_data(fake_vllm: FakeVllm) -> None:
    echoed = f"invalid image_url: data:image/png;base64,{PNG} " + "x" * 2000
    fake_vllm.overrides["/v1/chat/completions"] = httpx.Response(
        400, json={"error": {"message": echoed}}
    )

    with pytest.raises(BackendRequestError) as raised:
        asyncio.run(_backend(fake_vllm).chat(_request()))

    assert PNG not in str(raised.value)
    assert "[image data removed]" in str(raised.value)
    assert len(str(raised.value)) < 400
