"""Shared fixtures. Tests never touch a real Lemonade server or the network."""

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from antar.config.settings import CONFIG_FILE_ENV, Settings, StorageSettings

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
        {"id": "Some-Future-Model", "recipe": "new-recipe", "labels": ["mesh-thing"]},
    ],
}

Handler = Callable[[httpx.Request], httpx.Response]


def lemonade_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/health":
        return httpx.Response(200, json=LEMONADE_HEALTH)
    if request.url.path == "/v1/models":
        return httpx.Response(200, json=LEMONADE_MODELS)
    return httpx.Response(404, text=json.dumps({"error": "not found"}))


def refuse_connection(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


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
    ):
        monkeypatch.delenv(name, raising=False)
    return Settings(
        _env_file=None,
        storage=StorageSettings(experiments_dir=tmp_path / "experiments"),
    )
