"""HTTP client for a self-hosted vLLM OpenAI-compatible server.

Checked against the vLLM documentation (https://docs.vllm.ai/en/stable/) on
2026-11-18. **Not yet exercised against a live server** — see
``docs/phase2-amd-cloud.md`` for the remaining live verification.

Documented, and relied on here:

* Endpoints ``/health``, ``/version``, ``/v1/models``, ``/v1/chat/completions``
  (serving/online_serving). ``/health`` and ``/version`` live at the server
  root, beside ``/v1``. ``/health`` answers 503 while a model is loading
  (AMD "Serving LLMs on Instinct" walkthrough).
* Image input follows the OpenAI vision format: ``image_url`` content parts,
  several per message for multi-image prompts (features/multimodal_inputs).
* Reasoning arrives separately as ``reasoning``; older releases called the
  field ``reasoning_content`` (features/reasoning_outputs). Both are read.

Not stated on the pages read, so handled leniently and to be confirmed live:

* The exact ``/v1/models`` entry shape. Only ``id`` is required here;
  ``root`` and ``max_model_len`` are used when present.
* The body of an authentication failure. Any 401 is treated as one.
* Turning thinking off per request. ``chat_template_kwargs`` is what the Qwen3
  model cards show for vLLM; the server-side equivalent
  (``--default-chat-template-kwargs``) is documented.

vLLM reports token usage for a response but no per-response timings, so every
duration in ``InferenceMetrics`` for this backend is measured by Antar.
"""

import json
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from antar.core.errors import BackendRequestError, BackendUnavailableError, ModelNotFoundError
from antar.inference.openai import (
    as_dict,
    as_int,
    error_message,
    parse_sse_data,
    to_openai_message,
)
from antar.inference.types import ChatDelta, ChatRequest, InferenceMetrics

_OOM_MARKERS = ("out of memory", "outofmemory")
_MAX_ERROR_CHARS = 300
_DATA_URL = re.compile(r"data:[^;,\s]+;base64,[A-Za-z0-9+/=]+")


def _safe_error(body: object, fallback: str) -> str:
    """Upstream error text, bounded and with any echoed image data removed.

    Servers sometimes quote the offending input in a validation error; an image
    must not reach a log, a report, or the browser that way.
    """
    message, _ = error_message(body, fallback)
    message = _DATA_URL.sub("[image data removed]", message)
    if len(message) > _MAX_ERROR_CHARS:
        message = message[:_MAX_ERROR_CHARS] + "…"
    if any(marker in message.lower() for marker in _OOM_MARKERS):
        message = f"GPU memory exhausted on the cloud host: {message}"
    return message


class VllmModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(min_length=1)
    root: str | None = None
    max_model_len: int | None = None


class VllmCompletion(BaseModel):
    """The parts of a finished chat completion that Antar uses."""

    model_config = ConfigDict(frozen=True)

    content: str
    reasoning: str | None
    finish_reason: str | None
    metrics: InferenceMetrics


def build_chat_payload(request: ChatRequest, *, stream: bool) -> dict[str, Any]:
    settings = request.settings
    payload: dict[str, Any] = {
        "model": request.model,
        "messages": [to_openai_message(message) for message in request.messages],
        "max_tokens": settings.max_tokens,
        "stream": stream,
    }
    optional = {
        "temperature": settings.temperature,
        "top_p": settings.top_p,
        "seed": settings.seed,
    }
    payload.update({key: value for key, value in optional.items() if value is not None})
    if settings.enable_thinking is not None:
        payload["chat_template_kwargs"] = {"enable_thinking": settings.enable_thinking}
    if stream:
        payload["stream_options"] = {"include_usage": True}
    return payload


def _metrics(usage: object, latency_ms: float, first_chunk_ms: float | None) -> InferenceMetrics:
    usage_map = as_dict(usage)
    cached = as_dict(usage_map.get("prompt_tokens_details")).get("cached_tokens")
    return InferenceMetrics(
        latency_ms=latency_ms,
        first_chunk_ms=first_chunk_ms,
        prompt_tokens=as_int(usage_map.get("prompt_tokens")),
        completion_tokens=as_int(usage_map.get("completion_tokens")),
        cached_prompt_tokens=as_int(cached),
    )


def _reasoning(source: dict[str, Any]) -> str:
    value = source.get("reasoning") or source.get("reasoning_content") or ""
    return value if isinstance(value, str) else ""


class VllmClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 5.0,
        generation_timeout_seconds: float = 600.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        # /health and /version are served beside /v1, not under it.
        self.root_url = self.base_url.removesuffix("/v1")
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout_seconds
        self._generation_timeout = generation_timeout_seconds
        self._transport = transport

    def _client(self, read_timeout: float) -> httpx.AsyncClient:
        timeout = httpx.Timeout(read_timeout, connect=self._timeout)
        # trust_env=False: proxy variables in the environment must not reroute the key or
        # images away from the one configured destination.
        return httpx.AsyncClient(
            headers=self._headers, timeout=timeout, transport=self._transport, trust_env=False
        )

    def _unreachable(self, url: str) -> BackendUnavailableError:
        return BackendUnavailableError(
            f"Could not connect to the cloud endpoint at {url}. Is the SSH tunnel open and "
            "vLLM running?"
        )

    def _raise_for_error(self, response: httpx.Response, body: object) -> None:
        if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
            raise BackendUnavailableError(
                f"The cloud endpoint rejected the request ({response.status_code}). Set "
                "ANTAR_CLOUD__API_KEY to the key vLLM was started with."
            )
        if not response.is_error:
            return
        message = _safe_error(body, f"vLLM returned HTTP {response.status_code}.")
        if response.status_code == httpx.codes.NOT_FOUND:
            raise ModelNotFoundError(f"vLLM: {message}")
        raise BackendRequestError(f"vLLM error (HTTP {response.status_code}): {message}")

    async def _get(self, url: str) -> httpx.Response:
        try:
            async with self._client(self._timeout) as client:
                return await client.get(url)
        except httpx.TimeoutException as exc:
            raise BackendUnavailableError(
                f"The cloud endpoint did not respond within {self._timeout:g}s at {url}."
            ) from exc
        except httpx.HTTPError as exc:
            raise self._unreachable(url) from exc

    async def health(self) -> float:
        """Check ``/health`` and return the round-trip time in milliseconds."""
        url = f"{self.root_url}/health"
        started = time.perf_counter()
        response = await self._get(url)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if response.status_code == httpx.codes.SERVICE_UNAVAILABLE:
            raise BackendUnavailableError("vLLM is starting: the model is still loading (503).")
        if response.is_error:
            raise BackendUnavailableError(f"{url} returned HTTP {response.status_code}.")
        return elapsed_ms

    async def version(self) -> str | None:
        """The vLLM version, or None if the server does not report one."""
        try:
            body: object = (await self._get(f"{self.root_url}/version")).json()
        except (BackendUnavailableError, ValueError):
            return None
        version = as_dict(body).get("version")
        return version if isinstance(version, str) and version else None

    async def list_models(self) -> tuple[VllmModel, ...]:
        url = f"{self.base_url}/models"
        response = await self._get(url)
        try:
            body: object = response.json()
        except ValueError as exc:
            if response.is_error:
                self._raise_for_error(response, None)
            raise BackendUnavailableError(
                f"{url} did not return JSON. Check that the URL points at vLLM and includes /v1."
            ) from exc
        self._raise_for_error(response, body)
        entries = as_dict(body).get("data")
        if not isinstance(entries, list):
            raise BackendUnavailableError("Unexpected response from the cloud endpoint /models.")
        models: list[VllmModel] = []
        for entry in entries:
            try:
                models.append(VllmModel.model_validate(entry))
            except ValidationError:
                continue
        return tuple(models)

    async def chat(self, request: ChatRequest) -> VllmCompletion:
        url = f"{self.base_url}/chat/completions"
        started = time.perf_counter()
        try:
            async with self._client(self._generation_timeout) as client:
                response = await client.post(url, json=build_chat_payload(request, stream=False))
        except httpx.TimeoutException as exc:
            raise BackendUnavailableError(
                f"The cloud endpoint did not answer within {self._generation_timeout:g}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise self._unreachable(url) from exc
        latency_ms = (time.perf_counter() - started) * 1000
        try:
            body: object = response.json()
        except ValueError:
            body = None
        self._raise_for_error(response, body)
        choices = as_dict(body).get("choices")
        if not isinstance(choices, list) or not choices:
            raise BackendRequestError("vLLM returned a completion with no choices.")
        choice = as_dict(choices[0])
        message = as_dict(choice.get("message"))
        return VllmCompletion(
            content=message.get("content") or "",
            reasoning=_reasoning(message) or None,
            finish_reason=choice.get("finish_reason"),
            metrics=_metrics(as_dict(body).get("usage"), latency_ms, None),
        )

    async def chat_stream(
        self, request: ChatRequest
    ) -> AsyncGenerator[ChatDelta | VllmCompletion, None]:
        """Yield deltas as they arrive, then one ``VllmCompletion``.

        Closing this generator closes the HTTP connection, which makes vLLM
        abort the request.
        """
        url = f"{self.base_url}/chat/completions"
        started = time.perf_counter()
        first_chunk_ms: float | None = None
        content: list[str] = []
        reasoning: list[str] = []
        finish_reason: str | None = None
        usage: object = None

        try:
            async with (
                self._client(self._generation_timeout) as client,
                client.stream(
                    "POST", url, json=build_chat_payload(request, stream=True)
                ) as response,
            ):
                if response.is_error:
                    raw = await response.aread()
                    try:
                        error_body: object = json.loads(raw)
                    except ValueError:
                        error_body = None
                    self._raise_for_error(response, error_body)

                async for line in response.aiter_lines():
                    chunk = parse_sse_data(line)
                    if chunk is None:
                        continue
                    if "error" in chunk:
                        message = _safe_error(chunk, "vLLM reported a stream error.")
                        raise BackendRequestError(f"vLLM error during generation: {message}")
                    usage = chunk.get("usage") or usage
                    choices = chunk.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = as_dict(choices[0])
                    finish_reason = choice.get("finish_reason") or finish_reason
                    delta = as_dict(choice.get("delta"))
                    text = delta.get("content") or ""
                    thought = _reasoning(delta)
                    if not text and not thought:
                        continue
                    if first_chunk_ms is None:
                        first_chunk_ms = (time.perf_counter() - started) * 1000
                    content.append(text)
                    reasoning.append(thought)
                    yield ChatDelta(content=text, reasoning=thought)
        except httpx.TimeoutException as exc:
            raise BackendUnavailableError(
                f"The cloud endpoint stopped responding for {self._generation_timeout:g}s "
                "during generation."
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendUnavailableError(
                f"Lost the connection to the cloud endpoint at {url}. Is the SSH tunnel still open?"
            ) from exc

        yield VllmCompletion(
            content="".join(content),
            reasoning="".join(reasoning) or None,
            finish_reason=finish_reason,
            metrics=_metrics(usage, (time.perf_counter() - started) * 1000, first_chunk_ms),
        )
