"""Lemonade chat, streaming, and model management, against a recorded fake server."""

import asyncio
import base64

import httpx
import pytest

from antar.backends.lemonade.backend import LemonadeBackend, parse_quantization
from antar.backends.lemonade.client import LemonadeClient, build_chat_payload
from antar.core.errors import (
    BackendRequestError,
    BackendUnavailableError,
    CapabilityNotSupportedError,
    ModelNotDownloadedError,
    ModelNotFoundError,
)
from antar.inference.openai import parse_sse_data
from antar.inference.types import (
    ChatDone,
    ChatEvent,
    ChatMessage,
    ChatRequest,
    GenerationSettings,
    ImageInput,
)
from tests.conftest import FakeLemonade, chunk, sse

TEXT_MODEL = "Qwen3-0.6B-GGUF"
VISION_MODEL = "Tiny-VLM-GGUF"
NOT_DOWNLOADED = "Gemma-3-4b-it-GGUF"
IMAGE = ImageInput(media_type="image/png", data_base64=base64.b64encode(b"png").decode())


def _backend(fake: FakeLemonade, api_key: str | None = None) -> LemonadeBackend:
    return LemonadeBackend(LemonadeClient(api_key=api_key, transport=httpx.MockTransport(fake)))


def _request(model: str = TEXT_MODEL, *, image: bool = False, **settings: object) -> ChatRequest:
    message = ChatMessage(role="user", content="What is 2+2?", images=(IMAGE,) if image else ())
    return ChatRequest(
        model=model,
        messages=(message,),
        settings=GenerationSettings.model_validate(settings),
    )


async def _collect(backend: LemonadeBackend, request: ChatRequest) -> list[ChatEvent]:
    return [event async for event in backend.chat_stream(request)]


def test_chat_returns_content_reasoning_and_backend_reported_metrics(
    fake_lemonade: FakeLemonade,
) -> None:
    result = asyncio.run(_backend(fake_lemonade).chat(_request()))

    assert result.content == "4"
    assert result.reasoning == "2+2 is 4."
    assert result.finish_reason == "stop"
    assert result.simulated is False
    metrics = result.metrics
    assert (metrics.prompt_tokens, metrics.completion_tokens) == (20, 12)
    assert metrics.cached_prompt_tokens == 3
    assert metrics.prompt_processing_ms == 49.3
    assert metrics.generation_ms == 120.0
    assert metrics.tokens_per_second == 100.0
    assert metrics.first_chunk_ms is None
    assert metrics.latency_ms >= 0


def test_metrics_stay_unavailable_when_the_backend_reports_no_timings(
    fake_lemonade: FakeLemonade,
) -> None:
    body = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
    fake_lemonade.overrides[("POST", "/v1/chat/completions")] = httpx.Response(200, json=body)

    metrics = asyncio.run(_backend(fake_lemonade).chat(_request())).metrics

    assert metrics.tokens_per_second is None
    assert metrics.completion_tokens is None
    assert metrics.prompt_processing_ms is None


def test_chat_payload_sends_only_settings_that_were_set() -> None:
    payload = build_chat_payload(_request(temperature=0.2, max_tokens=64), stream=False)

    assert payload == {
        "model": TEXT_MODEL,
        "messages": [{"role": "user", "content": "What is 2+2?"}],
        "max_tokens": 64,
        "stream": False,
        "temperature": 0.2,
    }


def test_stream_payload_requests_usage_and_can_disable_thinking() -> None:
    payload = build_chat_payload(_request(enable_thinking=False), stream=True)

    assert payload["stream_options"] == {"include_usage": True}
    assert payload["enable_thinking"] is False


def test_image_is_sent_as_openai_image_url_data_url() -> None:
    payload = build_chat_payload(_request(VISION_MODEL, image=True), stream=False)

    assert payload["messages"][0]["content"] == [
        {"type": "text", "text": "What is 2+2?"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{IMAGE.data_base64}"}},
    ]


def test_stream_yields_deltas_then_one_result_with_metrics(fake_lemonade: FakeLemonade) -> None:
    events = asyncio.run(_collect(_backend(fake_lemonade), _request()))

    deltas, done = events[:-1], events[-1]
    assert [(d.type, d.content, d.reasoning) for d in deltas if d.type == "delta"] == [
        ("delta", "", "Think"),
        ("delta", "", "ing."),
        ("delta", "Hel", ""),
        ("delta", "lo", ""),
    ]
    assert isinstance(done, ChatDone)
    assert done.result.content == "Hello"
    assert done.result.reasoning == "Thinking."
    assert done.result.finish_reason == "stop"
    assert done.result.metrics.tokens_per_second == 100.0
    assert done.result.metrics.first_chunk_ms is not None


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('data: {"a": 1}', {"a": 1}),
        ("data: [DONE]", None),
        ("", None),
        (": keep-alive comment", None),
        ("data: {not json", None),
        ("data: [1, 2]", None),
        ("event: message", None),
    ],
)
def test_parse_sse_data_ignores_everything_but_json_objects(
    line: str, expected: dict[str, int] | None
) -> None:
    assert parse_sse_data(line) == expected


def test_stream_raises_when_lemonade_reports_an_error_mid_generation(
    fake_lemonade: FakeLemonade,
) -> None:
    body = sse(chunk({"content": "Hi"}), {"error": {"message": "out of memory"}})
    fake_lemonade.overrides[("POST", "/v1/chat/completions")] = httpx.Response(200, content=body)

    with pytest.raises(BackendRequestError, match="out of memory"):
        asyncio.run(_collect(_backend(fake_lemonade), _request()))


def test_stream_maps_http_error_before_any_event(fake_lemonade: FakeLemonade) -> None:
    error = {"error": {"message": "Failed to load model: insufficient memory", "code": "x"}}
    fake_lemonade.overrides[("POST", "/v1/chat/completions")] = httpx.Response(500, json=error)

    with pytest.raises(BackendRequestError, match="insufficient memory"):
        asyncio.run(_collect(_backend(fake_lemonade), _request()))


def test_closing_the_stream_closes_the_connection_to_lemonade() -> None:
    closed = asyncio.Event()

    class EndlessStream(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            while True:
                yield sse(chunk({"content": "x"}))[: -len(b"data: [DONE]\n\n")]
                await asyncio.sleep(0)

        async def aclose(self) -> None:
            closed.set()

    fake = FakeLemonade()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(200, stream=EndlessStream())
        return fake(request)

    backend = LemonadeBackend(LemonadeClient(transport=httpx.MockTransport(handler)))

    async def cancel_after_first_delta() -> None:
        stream = backend.chat_stream(_request())
        async for _ in stream:
            break
        await stream.aclose()

    asyncio.run(cancel_after_first_delta())

    assert closed.is_set()


def test_connection_failure_during_chat_is_reported_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = LemonadeClient(transport=httpx.MockTransport(handler))

    with pytest.raises(BackendUnavailableError, match="Could not connect to Lemonade"):
        asyncio.run(client.chat(_request()))


def test_authentication_failure_names_the_setting_to_fix(fake_lemonade: FakeLemonade) -> None:
    denied = httpx.Response(401, json={"error": "Invalid or missing API key"})
    fake_lemonade.overrides[("POST", "/v1/chat/completions")] = denied

    with pytest.raises(BackendUnavailableError, match="ANTAR_LEMONADE__API_KEY"):
        asyncio.run(_backend(fake_lemonade).chat(_request()))


def test_model_not_found_error_code_is_mapped() -> None:
    error = {"error": {"message": "Model 'x' was not found.", "code": "model_not_found"}}
    client = LemonadeClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(404, json=error))
    )

    with pytest.raises(ModelNotFoundError, match="was not found"):
        asyncio.run(client.load("x"))


async def _attempt(backend: LemonadeBackend, action: str) -> None:
    if action == "chat":
        await backend.chat(_request(NOT_DOWNLOADED))
    elif action == "stream":
        await _collect(backend, _request(NOT_DOWNLOADED))
    else:
        await backend.load_model(NOT_DOWNLOADED)


@pytest.mark.parametrize("action", ["chat", "stream", "load"])
def test_nothing_is_sent_for_a_model_that_is_not_downloaded(
    fake_lemonade: FakeLemonade, action: str
) -> None:
    """Lemonade would download the model implicitly, so the request must never be made."""
    backend = _backend(fake_lemonade)

    with pytest.raises(ModelNotDownloadedError, match="not downloaded"):
        asyncio.run(_attempt(backend, action))

    assert not [request for request in fake_lemonade.requests if request[0] == "POST"]


def test_unknown_model_is_rejected_before_any_request(fake_lemonade: FakeLemonade) -> None:
    with pytest.raises(ModelNotFoundError):
        asyncio.run(_backend(fake_lemonade).chat(_request("No-Such-Model")))

    assert fake_lemonade.posts("/v1/chat/completions") == []


def test_image_is_refused_for_a_model_without_vision(fake_lemonade: FakeLemonade) -> None:
    with pytest.raises(CapabilityNotSupportedError, match="does not accept images"):
        asyncio.run(_backend(fake_lemonade).chat(_request(TEXT_MODEL, image=True)))

    assert fake_lemonade.posts("/v1/chat/completions") == []


def test_image_is_accepted_for_a_vision_model(fake_lemonade: FakeLemonade) -> None:
    asyncio.run(_backend(fake_lemonade).chat(_request(VISION_MODEL, image=True)))

    (sent,) = fake_lemonade.posts("/v1/chat/completions")
    assert sent["model"] == VISION_MODEL


def test_load_and_unload_use_the_documented_request_body(fake_lemonade: FakeLemonade) -> None:
    backend = _backend(fake_lemonade)

    asyncio.run(backend.load_model(VISION_MODEL))
    models = {model.id: model for model in asyncio.run(backend.list_models())}
    asyncio.run(backend.unload_model(VISION_MODEL))

    assert fake_lemonade.posts("/v1/load") == [{"model_name": VISION_MODEL}]
    assert fake_lemonade.posts("/v1/unload") == [{"model_name": VISION_MODEL}]
    assert models[VISION_MODEL].loaded is True
    assert models[TEXT_MODEL].loaded is False


def test_download_starts_a_server_owned_job_only_when_asked(fake_lemonade: FakeLemonade) -> None:
    backend = _backend(fake_lemonade)

    asyncio.run(backend.download_model(NOT_DOWNLOADED))
    (job,) = asyncio.run(backend.downloads())

    assert fake_lemonade.posts("/v1/pull") == [
        {"model_name": NOT_DOWNLOADED, "stream": True, "subscribe": False}
    ]
    assert (job.model, job.status, job.percent) == (NOT_DOWNLOADED, "downloading", 40)


def test_download_rejects_a_model_outside_the_catalog(fake_lemonade: FakeLemonade) -> None:
    with pytest.raises(ModelNotFoundError):
        asyncio.run(_backend(fake_lemonade).download_model("org/arbitrary-repo"))

    assert fake_lemonade.posts("/v1/pull") == []


def test_model_metadata_includes_quantization_and_context(fake_lemonade: FakeLemonade) -> None:
    models = {model.id: model for model in asyncio.run(_backend(fake_lemonade).list_models())}

    assert models[TEXT_MODEL].quantization == "Q4_0"
    assert models[VISION_MODEL].quantization == "Q8_0"
    assert models[NOT_DOWNLOADED].context_length == 8192


@pytest.mark.parametrize(
    ("checkpoint", "expected"),
    [
        ("unsloth/Qwen3-1.7B-GGUF:Q4_0", "Q4_0"),
        ("ggml-org/gemma-3-4b-it-GGUF:Q4_K_M", "Q4_K_M"),
        ("OpenBMB/MiniCPM-V-4-gguf:ggml-model-Q4_K_M.gguf", "Q4_K_M"),
        ("org/repo:model-f16.gguf", "F16"),
        ("ggerganov/whisper.cpp:ggml-tiny.bin", None),
        ("lemonade-sdk/some-onnx-model", None),
        (None, None),
    ],
)
def test_parse_quantization_reads_only_what_the_checkpoint_names(
    checkpoint: str | None, expected: str | None
) -> None:
    assert parse_quantization(checkpoint) == expected
