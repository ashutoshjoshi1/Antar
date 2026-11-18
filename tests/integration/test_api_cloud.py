"""Cloud and Comparison Lab routes through the real app, with every remote side stubbed."""

import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from antar_api.main import create_app
from antar_cli.main import app as cli_app
from fastapi.testclient import TestClient
from pydantic import HttpUrl, SecretStr
from typer.testing import CliRunner

from antar.backends.amd_cloud.amd_smi import GPU_COMMAND
from antar.backends.amd_cloud.config import AmdCloudProfile, CloudEndpointSettings
from antar.backends.amd_cloud.preflight import PREFLIGHT_COMMAND
from antar.backends.registry import build_backends
from antar.config.settings import Settings
from tests.conftest import CLOUD_URL, VLLM_KEY, FakeLemonade, FakeRunner, FakeVllm
from tests.unit.test_cloud_host import PREFLIGHT_OUTPUT, _amd_smi

API = "/api/v1"
CHAT = {
    "backend": "amd_cloud",
    "model": "Qwen/Qwen3-8B",
    "messages": [{"role": "user", "content": "hi"}],
}
COMPARISON = {
    "name": "tiny vs 8B",
    "local": {"backend": "lemonade", "model": {"id": "Qwen3-0.6B-GGUF"}},
    "cloud": {"backend": "amd_cloud", "model": {"id": "Qwen/Qwen3-8B"}},
    "workloads": ["qa_exact"],
    "warmup_runs": 0,
    "measured_runs": 1,
}


class Stack:
    def __init__(self, settings: Settings, *, cloud: bool = True, ssh: bool = True) -> None:
        self.lemonade = FakeLemonade()
        self.vllm = FakeVllm(key=VLLM_KEY)
        self.runner = FakeRunner({GPU_COMMAND: _amd_smi(), PREFLIGHT_COMMAND: PREFLIGHT_OUTPUT})
        endpoint = CloudEndpointSettings(
            base_url=HttpUrl(CLOUD_URL),
            api_key=SecretStr(VLLM_KEY),
            vllm_image="vllm/vllm-openai-rocm:v0.34.0-rocm100",
        )
        self.settings = settings.model_copy(
            update={
                "cloud": endpoint if cloud else None,
                "amd_cloud": AmdCloudProfile(name="lab", ssh_host="amd-box") if ssh else None,
            }
        )
        backends = build_backends(
            self.settings,
            lemonade_transport=httpx.MockTransport(self.lemonade),
            cloud_transport=httpx.MockTransport(self.vllm),
            cloud_runner=self.runner if ssh else None,
        )
        self.client = TestClient(
            create_app(self.settings, backends, remote_runner=self.runner if ssh else None)
        )


@pytest.fixture
def stack(settings: Settings) -> Iterator[Stack]:
    built = Stack(settings)
    # Entering the client keeps one event loop alive, so background jobs make progress.
    with built.client:
        yield built


def _wait_for_comparison(client: TestClient) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        active = client.get(f"{API}/comparisons/active").json()["active"]
        if active["status"] != "running":
            return active  # type: ignore[no-any-return]
        time.sleep(0.01)
    raise AssertionError("the comparison did not finish")


def test_status_describes_the_connection_without_exposing_the_key(stack: Stack) -> None:
    response = stack.client.get(f"{API}/cloud/status")

    body = response.json()
    assert body["endpoint_configured"] is True
    assert body["loopback"] is True
    assert body["api_key_configured"] is True
    assert body["status"]["availability"] == "available"
    assert body["round_trip_ms"] >= 0
    assert [model["id"] for model in body["models"]] == ["Qwen/Qwen3-8B"]
    assert body["models"][0]["location"] == "cloud"
    assert VLLM_KEY not in response.text
    assert VLLM_KEY not in stack.client.get(f"{API}/settings").text


def test_an_unconfigured_cloud_is_reported_plainly_and_refuses_inference(
    settings: Settings,
) -> None:
    client = Stack(settings, cloud=False, ssh=False).client

    status = client.get(f"{API}/cloud/status").json()
    gpus = client.get(f"{API}/cloud/gpus").json()

    assert status["endpoint_configured"] is False
    assert status["status"]["availability"] == "not_configured"
    assert status["round_trip_ms"] is None
    assert (gpus["ssh_configured"], gpus["sample"]) == (False, None)
    assert "No SSH host" in gpus["reason"]
    assert client.post(f"{API}/inference/chat", json=CHAT).status_code == 503
    assert client.post(f"{API}/cloud/preflight").status_code == 503


def test_a_dropped_tunnel_is_a_status_and_the_app_keeps_serving(stack: Stack) -> None:
    stack.vllm.overrides["/health"] = httpx.Response(502)

    status = stack.client.get(f"{API}/cloud/status")

    assert status.status_code == 200
    assert status.json()["status"]["availability"] == "unavailable"
    assert status.json()["models"] == []
    models = stack.client.get(f"{API}/models").json()
    assert {model["backend"] for model in models["models"]} == {"lemonade", "mock"}


def test_cloud_inference_runs_through_the_same_chat_routes(stack: Stack) -> None:
    result = stack.client.post(f"{API}/inference/chat", json=CHAT)
    stream = stack.client.post(f"{API}/inference/chat/stream", json=CHAT)

    assert result.status_code == 200
    assert (result.json()["backend"], result.json()["content"]) == ("amd_cloud", "42")
    assert result.json()["metrics"]["tokens_per_second"] is None
    assert '"type":"delta"' in stream.text
    assert '"type":"done"' in stream.text
    assert stack.lemonade.posts("/v1/chat/completions") == []


def test_the_unified_inventory_marks_where_each_model_runs(stack: Stack) -> None:
    models = stack.client.get(f"{API}/models").json()["models"]

    locations = {model["backend"]: model["location"] for model in models}
    assert locations == {"lemonade": "local", "amd_cloud": "cloud", "mock": "mock"}
    states = {model["id"]: model["state"] for model in models}
    assert states["Qwen3-0.6B-GGUF"] == "loaded"
    assert states["Whisper-Tiny"] == "installed"
    assert states["Gemma-3-4b-it-GGUF"] == "discovered"
    assert states["Qwen/Qwen3-8B"] == "loaded"


def test_gpu_readings_come_from_the_host_and_are_not_over_polled(stack: Stack) -> None:
    first = stack.client.get(f"{API}/cloud/gpus").json()
    stack.client.get(f"{API}/cloud/gpus")

    assert first["interval_seconds"] == 10.0
    assert [gpu["name"] for gpu in first["sample"]["gpus"]] == ["AMD Instinct MI300X"] * 2
    assert stack.runner.commands.count(GPU_COMMAND) == 1


def test_preflight_returns_each_check_with_its_remediation(stack: Stack) -> None:
    body = stack.client.post(f"{API}/cloud/preflight").json()

    failed = [check for check in body["checks"] if check["status"] == "fail"]
    assert [check["id"] for check in failed] == ["docker_permissions"]
    assert failed[0]["remediation"].startswith("sudo usermod")
    assert body["facts"]["gpu_model"] == "AMD Instinct MI300X"


def test_feasibility_uses_catalog_facts_and_refuses_unknown_models(stack: Stack) -> None:
    body = {"model": "Qwen/Qwen3-32B", "gpu_memory_bytes": 192 * 1024**3}

    known = stack.client.post(f"{API}/cloud/feasibility", json=body)
    unknown = stack.client.post(f"{API}/cloud/feasibility", json={**body, "model": "acme/x"})

    assert known.json()["verdict"] == "fits"
    assert known.json()["weights_bytes"] == 65_524_328_560
    assert unknown.status_code == 404
    catalog = stack.client.get(f"{API}/cloud/catalog").json()["models"]
    assert "Qwen/Qwen3-VL-8B-Instruct" in [model["id"] for model in catalog]


def test_cost_is_entered_by_the_operator_and_persisted(stack: Stack, tmp_path: Path) -> None:
    empty = stack.client.get(f"{API}/cloud/cost").json()
    session = {
        "hourly_price_usd": 4.0,
        "credit_balance_usd": 50.0,
        "instance_started_at": "2026-11-18T10:00:00Z",
        "instance_stopped_at": "2026-11-18T12:30:00Z",
    }

    saved = stack.client.put(f"{API}/cloud/cost", json=session).json()

    assert empty["estimated_spend_usd"] is None
    assert saved["estimated_spend_usd"] == pytest.approx(10.0)
    assert saved["estimated_remaining_usd"] == pytest.approx(40.0)
    assert saved["running"] is False
    assert stack.client.get(f"{API}/cloud/cost").json()["hourly_price_usd"] == 4.0
    assert (tmp_path / "cloud" / "session.json").is_file()
    rejected = {**session, "instance_stopped_at": "2026-11-18T09:00:00Z"}
    assert stack.client.put(f"{API}/cloud/cost", json=rejected).status_code == 422


def test_a_comparison_needs_confirmation_then_runs_and_exports(stack: Stack) -> None:
    unconfirmed = stack.client.post(f"{API}/comparisons", json={"config": COMPARISON})
    with_url = {
        "config": {
            **COMPARISON,
            "cloud": {"backend": "http://evil.example/v1", "model": {"id": "x"}},
        }
    }
    injected = stack.client.post(
        f"{API}/comparisons", json={**with_url, "confirm_cloud_usage": True}
    )
    assert unconfirmed.status_code == 422
    assert injected.status_code == 422
    assert stack.vllm.chats() == []

    started = stack.client.post(
        f"{API}/comparisons", json={"config": COMPARISON, "confirm_cloud_usage": True}
    )
    assert started.status_code == 202
    finished = _wait_for_comparison(stack.client)
    report_id = finished["id"]

    assert finished["status"] == "completed"
    history = stack.client.get(f"{API}/comparisons").json()["comparisons"]
    assert [(item["id"], item["cloud_model"]) for item in history] == [(report_id, "Qwen/Qwen3-8B")]
    report = stack.client.get(f"{API}/comparisons/{report_id}").json()
    assert report["cloud"]["execution"] == "cloud"
    assert report["gpu"]["gpu_count"] == 2
    exports = {
        kind: stack.client.get(f"{API}/comparisons/{report_id}/export", params={"format": kind})
        for kind in ("json", "csv", "md")
    }
    assert exports["json"].json()["id"] == report_id
    assert exports["csv"].text.startswith("side,backend,model,index")
    assert exports["md"].headers["content-type"].startswith("text/markdown")
    assert "## Limitations" in exports["md"].text
    assert stack.client.get(f"{API}/comparisons/nope").status_code == 404


def test_a_plain_benchmark_of_a_cloud_model_also_needs_confirmation(stack: Stack) -> None:
    config = {
        "name": "cloud only",
        "backend": "amd_cloud",
        "model": {"id": "Qwen/Qwen3-8B"},
        "workloads": ["qa_exact"],
        "warmup_runs": 0,
        "measured_runs": 1,
    }

    refused = stack.client.post(f"{API}/benchmarks", json=config)
    accepted = stack.client.post(f"{API}/benchmarks", json={**config, "confirm_cloud_usage": True})

    assert refused.status_code == 422
    assert "paid instance time" in refused.json()["detail"]
    assert accepted.status_code == 202
    for _ in range(500):
        if stack.client.get(f"{API}/benchmarks/active").json()["active"]["status"] != "running":
            break
        time.sleep(0.01)
    (summary,) = stack.client.get(f"{API}/benchmarks").json()["benchmarks"]
    assert (summary["backend"], summary["status"]) == ("amd_cloud", "completed")
    assert len(stack.vllm.chats()) == 6


def test_lemonade_provider_registration_is_explicit_and_uses_the_configured_endpoint(
    stack: Stack,
) -> None:
    providers: list[dict[str, object]] = []

    def system_info(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"cloud": {"providers": providers}})

    def lemonade(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/system-info":
            return system_info(request)
        response = stack.lemonade(request)
        if request.url.path == "/v1/install":
            providers.append({"name": "antaramd", "base_url": CLOUD_URL, "models_discovered": 1})
            return httpx.Response(200, json={"status": "success"})
        if request.url.path in ("/v1/cloud/auth", "/v1/uninstall"):
            if request.url.path == "/v1/uninstall":
                providers.clear()
            return httpx.Response(200, json={"status": "success"})
        return response

    backends = build_backends(
        stack.settings,
        lemonade_transport=httpx.MockTransport(lemonade),
        cloud_transport=httpx.MockTransport(stack.vllm),
    )
    client = TestClient(create_app(stack.settings, backends))

    before = client.get(f"{API}/cloud/lemonade-provider").json()
    refused = client.post(f"{API}/cloud/lemonade-provider", json={})
    registered = client.post(f"{API}/cloud/lemonade-provider", json={"confirm": True})

    assert (before["supported"], before["provider"]) == (True, None)
    assert refused.status_code == 422
    assert registered.json()["provider"]["models_discovered"] == 1
    assert stack.lemonade.posts("/v1/install") == [
        {"backend": "cloud", "provider": "antaramd", "base_url": CLOUD_URL}
    ]
    # An http:// loopback tunnel needs Lemonade's explicit plaintext opt-in to carry a key.
    assert stack.lemonade.posts("/v1/cloud/auth") == [
        {"provider": "antaramd", "api_key": VLLM_KEY, "allow_insecure_http": True}
    ]
    assert VLLM_KEY not in registered.text
    removed = client.delete(f"{API}/cloud/lemonade-provider").json()
    assert removed["provider"] is None


def test_an_older_lemonade_without_cloud_routing_is_reported_not_assumed(stack: Stack) -> None:
    body = stack.client.get(f"{API}/cloud/lemonade-provider").json()

    assert body["lemonade_reachable"] is True
    assert body["supported"] is False
    refused = stack.client.post(f"{API}/cloud/lemonade-provider", json={"confirm": True})
    assert refused.status_code == 422
    assert stack.lemonade.posts("/v1/install") == []


def test_cli_estimate_prints_the_budget_and_rejects_unknown_models() -> None:
    runner = CliRunner()

    known = runner.invoke(cli_app, ["cloud-estimate", "Qwen/Qwen3-8B", "--gpu-memory-gb", "192"])
    unknown = runner.invoke(cli_app, ["cloud-estimate", "acme/x", "--gpu-memory-gb", "192"])

    assert known.exit_code == 0
    assert '"verdict": "fits"' in known.stdout
    assert unknown.exit_code == 1
