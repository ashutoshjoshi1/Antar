"""HTTP client for the Lemonade local server.

Written against the Lemonade API reference on the ``main`` branch of
https://github.com/lemonade-sdk/lemonade (``docs/api/``) and verified by hand
against a running Lemonade v2026.46.2 on macOS on 2026-11-16:

* Documented base URL is ``http://localhost:13305/v1``.
* ``GET /v1/health`` — status, version, loaded models.
* ``GET /v1/models`` — OpenAI-style list with Lemonade fields; ``show_all=true``
  also lists catalog models that are not downloaded.
* ``GET /v1/stats`` — statistics for the server's *most recent* request plus
  totals. Server-wide, so never used for per-request metrics.
* ``POST /v1/chat/completions`` — OpenAI-compatible. Every llama.cpp response
  (and the final streamed chunk) carries a ``timings`` object specific to that
  response, which is where per-request metrics come from. Reasoning arrives
  separately as ``reasoning_content``.
* ``POST /v1/load`` / ``POST /v1/unload`` — body ``{"model_name": ...}``.
  **``/load`` and ``/chat/completions`` download a missing model implicitly**,
  so callers must check ``downloaded`` first; see ``LemonadeBackend``.
* ``POST /v1/pull`` with ``stream: true, subscribe: false`` starts a
  server-owned download that ``GET /v1/downloads`` reports on.
* Optional auth: ``Authorization: Bearer <LEMONADE_API_KEY>``.
* Cloud providers (experimental in Lemonade; guide/configuration/cloud and the
  Lemonade API reference, exercised against v2026.46.2 on 2026-11-18 with a
  stand-in OpenAI-compatible server): ``POST /v1/install`` with
  ``{"backend": "cloud", "provider", "base_url"}`` registers one,
  ``POST /v1/cloud/auth`` stores a key in Lemonade's memory (an ``http://``
  provider needs ``allow_insecure_http: true``), ``POST /v1/uninstall``
  removes it, and ``GET /v1/system-info`` lists them under ``cloud.providers``.
  Discovered models appear as ``<provider>.<upstream id>`` with
  ``recipe: "cloud"`` and are relayed through ``/v1/chat/completions``.

Only the fields Antar uses are modelled; unknown fields are ignored so that
additive upstream changes do not break the adapter.
"""

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from antar.core.errors import BackendRequestError, BackendUnavailableError, ModelNotFoundError
from antar.inference.openai import (
    as_dict as _dict,
)
from antar.inference.openai import (
    as_float as _as_float,
)
from antar.inference.openai import (
    as_int as _as_int,
)
from antar.inference.openai import (
    error_message,
    parse_sse_data,
    to_openai_message,
)
from antar.inference.types import ChatDelta, ChatRequest, InferenceMetrics

logger = logging.getLogger(__name__)

DEFAULT_LEMONADE_BASE_URL = "http://localhost:13305/v1"


class LemonadeLoadedModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    model_name: str
    type: str | None = None
    device: str | None = None
    recipe: str | None = None
    status: str | None = None
    is_busy: bool | None = None
    pid: int | None = None


class LemonadeHealth(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    status: str
    version: str | None = None
    model_loaded: str | None = None
    all_models_loaded: tuple[LemonadeLoadedModel, ...] = ()


class LemonadeModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(min_length=1)
    checkpoint: str | None = None
    recipe: str | None = None
    size: float | None = Field(default=None, description="Size in GB; omitted when unknown.")
    downloaded: bool | None = None
    labels: tuple[str, ...] = ()
    max_context_window: int | None = None
    cloud_provider: str | None = Field(
        default=None, description="Set for models routed to a registered cloud provider."
    )


class LemonadeLiveStats(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    active_requests: int | None = None


class LemonadeStats(BaseModel):
    """Server-wide statistics: the latest request and totals since server start."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    time_to_first_token: float | None = None
    tokens_per_second: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_count_total: int | None = None
    output_tokens_total: int | None = None
    live: LemonadeLiveStats | None = None


class LemonadeDownload(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    model_name: str = ""
    status: str = "unknown"
    percent: float | None = None
    overall_bytes_downloaded: int | None = None
    total_download_size: int | None = None
    complete: bool = False


class LemonadeCloudProvider(BaseModel):
    """A cloud provider registered in Lemonade. Keys are never part of this."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str
    base_url: str | None = None
    env_var_set: bool | None = None
    runtime_key_set: bool | None = None
    models_discovered: int | None = None
    allow_insecure_http: bool | None = None
    warnings: tuple[str, ...] = ()


class LemonadeCompletion(BaseModel):
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
        "enable_thinking": settings.enable_thinking,
    }
    payload.update({key: value for key, value in optional.items() if value is not None})
    if stream:
        payload["stream_options"] = {"include_usage": True}
    return payload


def build_metrics(
    *, usage: object, timings: object, latency_ms: float, first_chunk_ms: float | None
) -> InferenceMetrics:
    """Combine Antar's clock with what the backend reported for this response."""
    usage_map = _dict(usage)
    timing_map = _dict(timings)
    cached = _dict(usage_map.get("prompt_tokens_details")).get("cached_tokens")
    return InferenceMetrics(
        latency_ms=latency_ms,
        first_chunk_ms=first_chunk_ms,
        prompt_tokens=_as_int(usage_map.get("prompt_tokens")),
        completion_tokens=_as_int(usage_map.get("completion_tokens")),
        cached_prompt_tokens=_as_int(cached),
        prompt_processing_ms=_as_float(timing_map.get("prompt_ms")),
        generation_ms=_as_float(timing_map.get("predicted_ms")),
        tokens_per_second=_as_float(timing_map.get("predicted_per_second")),
    )


class LemonadeClient:
    def __init__(
        self,
        base_url: str = DEFAULT_LEMONADE_BASE_URL,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 3.0,
        generation_timeout_seconds: float = 300.0,
        load_timeout_seconds: float = 600.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout_seconds
        self._generation_timeout = generation_timeout_seconds
        self._load_timeout = load_timeout_seconds
        self._transport = transport

    def _client(self, read_timeout: float) -> httpx.AsyncClient:
        # Connecting should be quick even when the read (generation) is slow.
        timeout = httpx.Timeout(read_timeout, connect=self._timeout)
        return httpx.AsyncClient(headers=self._headers, timeout=timeout, transport=self._transport)

    def _raise_for_error(self, response: httpx.Response, body: object) -> None:
        if response.status_code == httpx.codes.UNAUTHORIZED:
            raise BackendUnavailableError(
                "Lemonade rejected the request (401). Set ANTAR_LEMONADE__API_KEY to the "
                "server's LEMONADE_API_KEY."
            )
        if not response.is_error:
            return
        message, code = error_message(body, f"Lemonade returned HTTP {response.status_code}.")
        if code == "model_not_found":
            raise ModelNotFoundError(message)
        raise BackendRequestError(f"Lemonade error (HTTP {response.status_code}): {message}")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        read_timeout: float | None = None,
    ) -> object:
        url = f"{self.base_url}{path}"
        timeout = read_timeout if read_timeout is not None else self._timeout
        try:
            async with self._client(timeout) as client:
                response = await client.request(method, url, params=params, json=payload)
        except httpx.TimeoutException as exc:
            raise BackendUnavailableError(
                f"Lemonade did not respond within {timeout:g}s at {url}."
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendUnavailableError(
                f"Could not connect to Lemonade at {url}. Is the server installed and running?"
            ) from exc

        try:
            body: object = response.json()
        except ValueError as exc:
            if response.is_error:
                self._raise_for_error(response, None)
            raise BackendUnavailableError(
                f"{url} did not return JSON. Check that the URL points at a Lemonade server "
                "and includes the /v1 prefix."
            ) from exc
        self._raise_for_error(response, body)
        return body

    async def health(self) -> LemonadeHealth:
        payload = await self._request("GET", "/health")
        try:
            return LemonadeHealth.model_validate(payload)
        except ValidationError as exc:
            raise BackendUnavailableError(
                "Unexpected response from Lemonade /health; the server may be an "
                "incompatible version."
            ) from exc

    async def list_models(self, *, show_all: bool = False) -> tuple[LemonadeModel, ...]:
        payload = await self._request(
            "GET", "/models", params={"show_all": "true"} if show_all else None
        )
        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise BackendUnavailableError(
                "Unexpected response from Lemonade /models; the server may be an "
                "incompatible version."
            )
        models: list[LemonadeModel] = []
        for entry in entries:
            try:
                models.append(LemonadeModel.model_validate(entry))
            except ValidationError:
                # Skip the entry rather than lose the whole inventory.
                logger.warning("Skipping malformed Lemonade model entry: %r", entry)
        return tuple(models)

    async def stats(self) -> LemonadeStats:
        try:
            return LemonadeStats.model_validate(await self._request("GET", "/stats"))
        except ValidationError as exc:
            raise BackendUnavailableError("Unexpected response from Lemonade /stats.") from exc

    async def load(self, model_name: str) -> None:
        await self._request(
            "POST", "/load", payload={"model_name": model_name}, read_timeout=self._load_timeout
        )

    async def unload(self, model_name: str) -> None:
        await self._request("POST", "/unload", payload={"model_name": model_name})

    async def pull(self, model_name: str) -> None:
        """Start a server-owned download and return immediately."""
        await self._request(
            "POST",
            "/pull",
            payload={"model_name": model_name, "stream": True, "subscribe": False},
            read_timeout=self._load_timeout,
        )

    async def downloads(self) -> tuple[LemonadeDownload, ...]:
        payload = await self._request("GET", "/downloads")
        if not isinstance(payload, list):
            return ()
        jobs: list[LemonadeDownload] = []
        for entry in payload:
            try:
                jobs.append(LemonadeDownload.model_validate(entry))
            except ValidationError:
                logger.warning("Skipping malformed Lemonade download entry")
        return tuple(jobs)

    async def cloud_providers(self) -> tuple[LemonadeCloudProvider, ...] | None:
        """Registered cloud providers, or None if this Lemonade has no cloud routing."""
        try:
            body = await self._request("GET", "/system-info")
        except (BackendRequestError, ModelNotFoundError):
            # The server answered but has no such endpoint: an older Lemonade.
            return None
        cloud = body.get("cloud") if isinstance(body, dict) else None
        if not isinstance(cloud, dict) or not isinstance(cloud.get("providers"), list):
            return None
        providers: list[LemonadeCloudProvider] = []
        for entry in cloud["providers"]:
            try:
                providers.append(LemonadeCloudProvider.model_validate(entry))
            except ValidationError:
                logger.warning("Skipping malformed Lemonade cloud provider entry")
        return tuple(providers)

    async def install_cloud_provider(self, provider: str, base_url: str) -> None:
        await self._request(
            "POST",
            "/install",
            payload={"backend": "cloud", "provider": provider, "base_url": base_url},
            read_timeout=self._load_timeout,
        )

    async def set_cloud_provider_key(
        self, provider: str, api_key: str, *, allow_insecure_http: bool
    ) -> None:
        """Hand Lemonade a key for a provider. Lemonade keeps it in memory only."""
        await self._request(
            "POST",
            "/cloud/auth",
            payload={
                "provider": provider,
                "api_key": api_key,
                "allow_insecure_http": allow_insecure_http,
            },
            read_timeout=self._load_timeout,
        )

    async def uninstall_cloud_provider(self, provider: str) -> None:
        await self._request(
            "POST", "/uninstall", payload={"backend": "cloud", "provider": provider}
        )

    async def chat(self, request: ChatRequest) -> LemonadeCompletion:
        started = time.perf_counter()
        body = await self._request(
            "POST",
            "/chat/completions",
            payload=build_chat_payload(request, stream=False),
            read_timeout=self._generation_timeout,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        choices = body.get("choices") if isinstance(body, dict) else None
        if not isinstance(body, dict) or not isinstance(choices, list) or not choices:
            raise BackendRequestError("Lemonade returned a completion with no choices.")
        choice = _dict(choices[0])
        message = _dict(choice.get("message"))
        reasoning = message.get("reasoning_content")
        return LemonadeCompletion(
            content=message.get("content") or "",
            reasoning=reasoning if isinstance(reasoning, str) and reasoning else None,
            finish_reason=choice.get("finish_reason"),
            metrics=build_metrics(
                usage=body.get("usage"),
                timings=body.get("timings"),
                latency_ms=latency_ms,
                first_chunk_ms=None,
            ),
        )

    async def chat_stream(
        self, request: ChatRequest
    ) -> AsyncGenerator[ChatDelta | LemonadeCompletion, None]:
        """Yield deltas as they arrive, then one ``LemonadeCompletion``.

        Closing this generator closes the HTTP connection, which is how an
        in-flight generation is cancelled on the Lemonade side.
        """
        url = f"{self.base_url}/chat/completions"
        started = time.perf_counter()
        first_chunk_ms: float | None = None
        content: list[str] = []
        reasoning: list[str] = []
        finish_reason: str | None = None
        usage: object = None
        timings: object = None

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
                        message, _ = error_message(chunk, "Lemonade reported a stream error.")
                        raise BackendRequestError(f"Lemonade error during generation: {message}")
                    usage = chunk.get("usage") or usage
                    timings = chunk.get("timings") or timings
                    choices = chunk.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = _dict(choices[0])
                    finish_reason = choice.get("finish_reason") or finish_reason
                    delta = _dict(choice.get("delta"))
                    text = delta.get("content") or ""
                    thought = delta.get("reasoning_content") or ""
                    if not text and not thought:
                        continue
                    if first_chunk_ms is None:
                        first_chunk_ms = (time.perf_counter() - started) * 1000
                    content.append(text)
                    reasoning.append(thought)
                    yield ChatDelta(content=text, reasoning=thought)
        except httpx.TimeoutException as exc:
            raise BackendUnavailableError(
                f"Lemonade stopped responding for {self._generation_timeout:g}s during generation."
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendUnavailableError(
                f"Lost the connection to Lemonade at {url}. Is the server still running?"
            ) from exc

        yield LemonadeCompletion(
            content="".join(content),
            reasoning="".join(reasoning) or None,
            finish_reason=finish_reason,
            metrics=build_metrics(
                usage=usage,
                timings=timings,
                latency_ms=(time.perf_counter() - started) * 1000,
                first_chunk_ms=first_chunk_ms,
            ),
        )
