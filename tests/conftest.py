"""Shared fixtures. Tests never touch a real Lemonade server or the network."""

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from antar.backends.amd_cloud.ssh import CommandResult
from antar.config.settings import CONFIG_FILE_ENV, Settings, StorageSettings
from antar.core.errors import BackendUnavailableError

REPO_ROOT = Path(__file__).resolve().parent.parent

# Trimmed from the documented examples in lemonade-sdk/lemonade docs/api/.
LEMONADE_HEALTH = {
    "status": "ok",
    "version": "2026.46.2",
    "model_loaded": "Qwen3-0.6B-GGUF",
    "all_models_loaded": [
        {"model_name": "Qwen3-0.6B-GGUF", "type": "llm", "device": "gpu", "recipe": "llamacpp"}
    ],
    "websocket_port": 9001,
}
LEMONADE_MODELS = {
    "object": "list",
    "data": [
        {
            "id": "Qwen3-0.6B-GGUF",
            "object": "model",
            "owned_by": "lemonade",
            "checkpoint": "unsloth/Qwen3-0.6B-GGUF:Q4_0",
            "recipe": "llamacpp",
            "size": 0.38,
            "downloaded": True,
            "labels": ["reasoning"],
        },
        {
            "id": "Gemma-3-4b-it-GGUF",
            "checkpoint": "ggml-org/gemma-3-4b-it-GGUF:Q4_K_M",
            "recipe": "llamacpp",
            "max_context_window": 8192,
            "downloaded": False,
            "labels": ["chat", "vision", "hot"],
        },
        {
            "id": "Whisper-Tiny",
            "checkpoint": "ggerganov/whisper.cpp:ggml-tiny.bin",
            "recipe": "whispercpp",
            "size": 0.075,
            "downloaded": True,
            "labels": ["transcription"],
        },
        {
            "id": "Tiny-VLM-GGUF",
            "checkpoint": "org/tiny-vlm-gguf:tiny-vlm-Q8_0.gguf",
            "recipe": "llamacpp",
            "size": 0.5,
            "downloaded": True,
            "labels": ["chat", "vision"],
        },
        {"id": "Some-Future-Model", "recipe": "new-recipe", "labels": ["mesh-thing"]},
    ],
}

Handler = Callable[[httpx.Request], httpx.Response]

COMPLETION = {
    "choices": [
        {
            "finish_reason": "stop",
            "index": 0,
            "message": {"role": "assistant", "content": "4", "reasoning_content": "2+2 is 4."},
        }
    ],
    "model": "Qwen3-0.6B-GGUF",
    "usage": {
        "completion_tokens": 12,
        "prompt_tokens": 20,
        "total_tokens": 32,
        "prompt_tokens_details": {"cached_tokens": 3},
    },
    "timings": {
        "cache_n": 3,
        "prompt_n": 17,
        "prompt_ms": 49.3,
        "predicted_n": 12,
        "predicted_ms": 120.0,
        "predicted_per_second": 100.0,
    },
}


def sse(*events: object) -> bytes:
    lines = [f"data: {json.dumps(event)}\n\n" for event in events]
    return ("".join(lines) + "data: [DONE]\n\n").encode()


def chunk(delta: dict[str, str], finish_reason: str | None = None) -> dict[str, object]:
    return {"choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}


STREAM = sse(
    chunk({"role": "assistant"}),
    chunk({"reasoning_content": "Think"}),
    chunk({"reasoning_content": "ing."}),
    chunk({"content": "Hel"}),
    chunk({"content": "lo"}),
    chunk({}, "stop"),
    {"choices": [], "usage": COMPLETION["usage"], "timings": COMPLETION["timings"]},
)


class FakeLemonade:
    """An in-memory stand-in for the Lemonade HTTP API that records what it was asked."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, object]]] = []
        self.loaded = ["Qwen3-0.6B-GGUF"]
        self.overrides: dict[tuple[str, str], httpx.Response] = {}

    def posts(self, path: str) -> list[dict[str, object]]:
        return [body for method, url, body in self.requests if method == "POST" and url == path]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        path = request.url.path
        self.requests.append((request.method, path, body))
        override = self.overrides.get((request.method, path))
        if override is not None:
            return override
        if path == "/v1/health":
            loaded = [{"model_name": name, "type": "llm", "pid": 4242} for name in self.loaded]
            return httpx.Response(200, json={**LEMONADE_HEALTH, "all_models_loaded": loaded})
        if path == "/v1/models":
            return httpx.Response(200, json=LEMONADE_MODELS)
        if path == "/v1/stats":
            return httpx.Response(200, json={"tokens_per_second": 100.0, "request_count_total": 3})
        if path == "/v1/downloads":
            job = {"model_name": "Gemma-3-4b-it-GGUF", "status": "downloading", "percent": 40}
            return httpx.Response(200, json=[job])
        if path == "/v1/chat/completions":
            if body.get("stream"):
                return httpx.Response(200, content=STREAM)
            return httpx.Response(200, json=COMPLETION)
        if path == "/v1/load":
            self.loaded = [str(body["model_name"])]
            return httpx.Response(200, json={"status": "success"})
        if path == "/v1/unload":
            self.loaded = []
            return httpx.Response(200, json={"status": "success"})
        if path == "/v1/pull":
            return httpx.Response(200, json={"status": "downloading"})
        return httpx.Response(404, json={"error": {"message": "not found", "code": "not_found"}})


def lemonade_handler(request: httpx.Request) -> httpx.Response:
    return FakeLemonade()(request)


def refuse_connection(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


VLLM_USAGE = {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15}
VLLM_KEY = "test-cloud-key"
CLOUD_URL = "http://127.0.0.1:18000/v1"


class FakeVllm:
    """An in-memory stand-in for a vLLM OpenAI-compatible server. No model, canned replies."""

    def __init__(self, models: tuple[str, ...] = ("Qwen/Qwen3-8B",), key: str | None = None):
        self.models = models
        self.key = key
        self.requests: list[tuple[str, str, dict[str, object]]] = []
        self.overrides: dict[str, httpx.Response] = {}
        self.health_status = 200

    def chats(self) -> list[dict[str, object]]:
        return [body for _, path, body in self.requests if path == "/v1/chat/completions"]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        path = request.url.path
        self.requests.append((request.method, path, body))
        if path in self.overrides:
            return self.overrides[path]
        if path == "/health":
            return httpx.Response(self.health_status)
        if path == "/version":
            return httpx.Response(200, json={"version": "0.34.0"})
        if self.key and request.headers.get("authorization") != f"Bearer {self.key}":
            return httpx.Response(401, json={"error": "Unauthorized"})
        if path == "/v1/models":
            data = [{"id": name, "root": name, "max_model_len": 32768} for name in self.models]
            return httpx.Response(200, json={"object": "list", "data": data})
        if path == "/v1/chat/completions":
            if body.get("stream"):
                return httpx.Response(
                    200,
                    content=sse(
                        chunk({"role": "assistant"}),
                        chunk({"reasoning": "Hm."}),
                        chunk({"content": "42"}),
                        chunk({}, "stop"),
                        {"choices": [], "usage": VLLM_USAGE},
                    ),
                )
            message = {"role": "assistant", "content": "42", "reasoning": "Hm."}
            choice = {"index": 0, "finish_reason": "stop", "message": message}
            return httpx.Response(200, json={"choices": [choice], "usage": VLLM_USAGE})
        return httpx.Response(404, json={"error": {"message": "not found"}})


class FakeRunner:
    """Stands in for SSH: returns canned output per command and records what was asked."""

    def __init__(self, outputs: dict[str, str] | None = None, error: str | None = None) -> None:
        self.outputs = outputs or {}
        self.error = error
        self.commands: list[str] = []
        self.stdin: list[bytes | None] = []

    async def run(self, command: str, *, stdin: bytes | None = None) -> CommandResult:
        self.commands.append(command)
        self.stdin.append(stdin)
        if self.error:
            raise BackendUnavailableError(self.error)
        return CommandResult(exit_code=0, stdout=self.outputs.get(command, ""), stderr="")


@pytest.fixture
def fake_vllm() -> FakeVllm:
    return FakeVllm()


@pytest.fixture
def fake_lemonade() -> FakeLemonade:
    return FakeLemonade()


@pytest.fixture
def lemonade_transport() -> httpx.MockTransport:
    return httpx.MockTransport(lemonade_handler)


@pytest.fixture
def offline_transport() -> httpx.MockTransport:
    return httpx.MockTransport(refuse_connection)


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings isolated from the developer's environment, .env, and YAML."""
    monkeypatch.setenv(CONFIG_FILE_ENV, str(tmp_path / "absent.yaml"))
    for name in (
        "ANTAR_LEMONADE__BASE_URL",
        "ANTAR_LEMONADE__API_KEY",
        "ANTAR_ENABLE_MOCK_BACKEND",
        "ANTAR_CLOUD__BASE_URL",
        "ANTAR_CLOUD__API_KEY",
        "ANTAR_CLOUD_COST__HOURLY_PRICE_USD",
        "ANTAR_CLOUD_COST__CREDIT_BALANCE_USD",
    ):
        monkeypatch.delenv(name, raising=False)
    return Settings(
        _env_file=None,
        storage=StorageSettings(
            experiments_dir=tmp_path / "experiments",
            benchmarks_dir=tmp_path / "benchmarks",
            comparisons_dir=tmp_path / "comparisons",
            cloud_dir=tmp_path / "cloud",
        ),
    )
