"""End-to-end API tests through the real app factory, with Lemonade stubbed at the transport."""

import httpx
import pytest
from antar_api.main import create_app
from antar_cli.main import app as cli_app
from fastapi.testclient import TestClient
from pydantic import SecretStr
from typer.testing import CliRunner

from antar.backends.registry import build_backends
from antar.config.settings import Settings


def _client(settings: Settings, transport: httpx.MockTransport) -> TestClient:
    backends = build_backends(settings, lemonade_transport=transport)
    return TestClient(create_app(settings, backends))


@pytest.fixture
def online(settings: Settings, lemonade_transport: httpx.MockTransport) -> TestClient:
    return _client(settings, lemonade_transport)


@pytest.fixture
def offline(settings: Settings, offline_transport: httpx.MockTransport) -> TestClient:
    return _client(settings, offline_transport)


def test_health_reports_ok_and_version(offline: TestClient) -> None:
    body = offline.get("/health").json()

    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


def test_system_returns_detected_hardware(offline: TestClient) -> None:
    response = offline.get("/api/v1/system")

    assert response.status_code == 200
    body = response.json()
    assert body["memory_total_bytes"] > 0
    assert body["cpu_model"]


def test_backends_report_lemonade_unavailable_without_failing(offline: TestClient) -> None:
    response = offline.get("/api/v1/backends")

    assert response.status_code == 200
    by_name = {backend["name"]: backend for backend in response.json()["backends"]}
    assert by_name["lemonade"]["availability"] == "unavailable"
    assert "Could not connect" in by_name["lemonade"]["detail"]
    assert by_name["amd_cloud"]["availability"] == "not_configured"
    assert by_name["mock"]["availability"] == "available"


def test_backends_report_lemonade_available_when_reachable(online: TestClient) -> None:
    by_name = {b["name"]: b for b in online.get("/api/v1/backends").json()["backends"]}

    assert by_name["lemonade"]["availability"] == "available"
    assert by_name["lemonade"]["version"] == "2026.46.2"


def test_models_fall_back_to_mock_inventory_when_lemonade_is_down(offline: TestClient) -> None:
    body = offline.get("/api/v1/models").json()

    assert {model["backend"] for model in body["models"]} == {"mock"}
    assert all(model["simulated"] for model in body["models"])


def test_models_include_lemonade_inventory_when_reachable(online: TestClient) -> None:
    body = online.get("/api/v1/models").json()

    lemonade = [model for model in body["models"] if model["backend"] == "lemonade"]
    assert len(lemonade) == 5
    assert not any(model["simulated"] for model in lemonade)


def test_capabilities_cover_all_modalities_and_do_not_overclaim(offline: TestClient) -> None:
    body = offline.get("/api/v1/capabilities").json()

    assert [m["modality"] for m in body["modalities"]] == [
        "text",
        "vision",
        "speech",
        "image",
        "video",
    ]
    supported = {
        (backend["backend"], capability["modality"])
        for backend in body["backends"]
        for capability in backend["capabilities"]
        if capability["support"] == "supported"
    }
    assert supported == {("mock", "text"), ("lemonade", "text"), ("lemonade", "vision")}
    assert not any(technique["implemented"] for technique in body["techniques"])


def test_settings_never_return_secrets(
    settings: Settings, offline_transport: httpx.MockTransport
) -> None:
    secret = settings.model_copy(
        update={
            "lemonade": settings.lemonade.model_copy(update={"api_key": SecretStr("super-secret")}),
        }
    )
    response = _client(secret, offline_transport).get("/api/v1/settings")

    assert response.status_code == 200
    assert "super-secret" not in response.text
    body = response.json()
    assert body["lemonade"]["api_key_configured"] is True
    assert body["lemonade"]["base_url"] == "http://localhost:13305/v1"
    assert body["amd_cloud"] is None


def test_experiments_are_empty_on_a_fresh_install(offline: TestClient) -> None:
    assert offline.get("/api/v1/experiments").json() == {"experiments": []}


def test_experiments_endpoint_survives_a_corrupt_record(
    settings: Settings, offline_transport: httpx.MockTransport
) -> None:
    directory = settings.storage.experiments_dir
    directory.mkdir(parents=True)
    (directory / "broken.json").write_text("{not json")

    response = _client(settings, offline_transport).get("/api/v1/experiments")

    assert response.status_code == 200
    assert response.json() == {"experiments": []}


def test_cli_mock_generate_rejects_empty_prompt_without_traceback() -> None:
    result = CliRunner().invoke(cli_app, ["mock-generate", ""])

    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_cors_allows_the_dev_frontend_only(offline: TestClient) -> None:
    allowed = offline.get("/health", headers={"Origin": "http://localhost:5173"})
    denied = offline.get("/health", headers={"Origin": "http://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers


def test_cli_mock_generate_outputs_simulated_result() -> None:
    result = CliRunner().invoke(cli_app, ["mock-generate", "hello world", "--seed", "3"])

    assert result.exit_code == 0
    assert '"simulated": true' in result.stdout


def test_cli_mock_generate_fails_cleanly_for_unknown_model() -> None:
    result = CliRunner().invoke(cli_app, ["mock-generate", "hi", "--model", "nope"])

    assert result.exit_code == 1
