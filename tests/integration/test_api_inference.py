"""Phase 1 API: model management, inference, streaming, telemetry, benchmarks."""

import base64
import json
import time
from collections.abc import Iterator

import httpx
import pytest
from antar_api.main import create_app
from fastapi.testclient import TestClient

from antar.backends.registry import build_backends
from antar.config.settings import Settings
from tests.conftest import FakeLemonade

TEXT_MODEL = "Qwen3-0.6B-GGUF"
VISION_MODEL = "Tiny-VLM-GGUF"
NOT_DOWNLOADED = "Gemma-3-4b-it-GGUF"
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()


@pytest.fixture
def client(settings: Settings, fake_lemonade: FakeLemonade) -> Iterator[TestClient]:
    backends = build_backends(settings, lemonade_transport=httpx.MockTransport(fake_lemonade))
    with TestClient(create_app(settings, backends)) as test_client:
        yield test_client


def _chat(model: str = TEXT_MODEL, **extra: object) -> dict[str, object]:
    return {"model": model, "messages": [{"role": "user", "content": "What is 2+2?"}], **extra}


def _events(response: httpx.Response) -> list[dict[str, object]]:
    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


def test_chat_returns_real_backend_result_with_metrics(client: TestClient) -> None:
    response = client.post("/api/v1/inference/chat", json=_chat())

    assert response.status_code == 200
    body = response.json()
    assert (body["content"], body["reasoning"], body["simulated"]) == ("4", "2+2 is 4.", False)
    assert body["metrics"]["tokens_per_second"] == 100.0
    assert body["metrics"]["first_chunk_ms"] is None


def test_chat_stream_emits_deltas_then_done(client: TestClient) -> None:
    response = client.post("/api/v1/inference/chat/stream", json=_chat())

    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)
    assert [event["type"] for event in events] == ["delta"] * 4 + ["done"]
    assert "".join(str(event["content"]) for event in events[:-1]) == "Hello"
    assert "".join(str(event["reasoning"]) for event in events[:-1]) == "Thinking."
    result = events[-1]["result"]
    assert isinstance(result, dict)
    assert result["content"] == "Hello"
    assert result["metrics"]["completion_tokens"] == 12


def test_chat_stream_reports_a_backend_failure_as_an_error_event(
    client: TestClient, fake_lemonade: FakeLemonade
) -> None:
    error = {"error": {"message": "Failed to load model: insufficient memory"}}
    fake_lemonade.overrides[("POST", "/v1/chat/completions")] = httpx.Response(500, json=error)

    (event,) = _events(client.post("/api/v1/inference/chat/stream", json=_chat()))

    assert event["type"] == "error"
    assert "insufficient memory" in str(event["message"])


def test_mock_backend_results_are_flagged_simulated(client: TestClient) -> None:
    response = client.post("/api/v1/inference/chat", json=_chat("mock/echo-small", backend="mock"))

    assert response.status_code == 200
    assert response.json()["simulated"] is True


def test_chat_never_falls_back_when_lemonade_is_down(
    settings: Settings, offline_transport: httpx.MockTransport
) -> None:
    backends = build_backends(settings, lemonade_transport=offline_transport)
    with TestClient(create_app(settings, backends)) as offline:
        response = offline.post("/api/v1/inference/chat", json=_chat())

    assert response.status_code == 503
    assert "Could not connect to Lemonade" in response.json()["detail"]


def test_vision_chat_forwards_the_image_to_a_vision_model(
    client: TestClient, fake_lemonade: FakeLemonade
) -> None:
    image = {"media_type": "image/png", "data_base64": PNG}
    message = {"role": "user", "content": "Describe this image.", "images": [image]}

    response = client.post(
        "/api/v1/inference/chat", json={"model": VISION_MODEL, "messages": [message]}
    )

    assert response.status_code == 200
    (sent,) = fake_lemonade.posts("/v1/chat/completions")
    parts = sent["messages"][0]["content"]  # type: ignore[index]
    assert parts[1]["image_url"]["url"] == f"data:image/png;base64,{PNG}"


@pytest.mark.parametrize(
    ("model", "image", "status", "fragment"),
    [
        (
            TEXT_MODEL,
            {"media_type": "image/png", "data_base64": PNG},
            422,
            "does not accept images",
        ),
        (VISION_MODEL, {"media_type": "image/jpeg", "data_base64": PNG}, 422, "declared as"),
        (VISION_MODEL, {"media_type": "image/png", "data_base64": "@@@"}, 422, "not valid base64"),
        (VISION_MODEL, {"media_type": "image/gif", "data_base64": PNG}, 422, ""),
    ],
)
def test_vision_chat_rejects_unusable_images(
    client: TestClient,
    fake_lemonade: FakeLemonade,
    model: str,
    image: dict[str, str],
    status: int,
    fragment: str,
) -> None:
    message = {"role": "user", "content": "What is this?", "images": [image]}

    response = client.post("/api/v1/inference/chat", json={"model": model, "messages": [message]})

    assert response.status_code == status
    assert fragment in json.dumps(response.json())
    assert fake_lemonade.posts("/v1/chat/completions") == []


def test_oversized_image_is_rejected(settings: Settings, fake_lemonade: FakeLemonade) -> None:
    small = settings.model_copy(update={"max_image_bytes": 16})
    backends = build_backends(small, lemonade_transport=httpx.MockTransport(fake_lemonade))
    image = {"media_type": "image/png", "data_base64": PNG}
    message = {"role": "user", "content": "x", "images": [image]}

    with TestClient(create_app(small, backends)) as limited:
        response = limited.post(
            "/api/v1/inference/chat", json={"model": VISION_MODEL, "messages": [message]}
        )

    assert response.status_code == 422
    assert "larger than" in response.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {"model": TEXT_MODEL, "messages": []},
        {"model": "", "messages": [{"role": "user", "content": "hi"}]},
        {"model": TEXT_MODEL, "messages": [{"role": "robot", "content": "hi"}]},
        {"model": TEXT_MODEL, "messages": [{"role": "user", "content": "  "}]},
        _chat(settings={"max_tokens": 0}),
        _chat(settings={"temperature": 9}),
        _chat(base_url="http://evil.example/v1"),
    ],
)
def test_chat_request_validation(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/api/v1/inference/chat", json=body).status_code == 422


def test_request_size_is_bounded(client: TestClient) -> None:
    image = {"media_type": "image/png", "data_base64": PNG}
    with_image = {"role": "user", "content": "x", "images": [image]}
    too_many_images = {"model": VISION_MODEL, "messages": [with_image] * 5}
    too_long = _chat()
    too_long["messages"] = [{"role": "user", "content": "x" * 200_001}]
    huge = client.post(
        "/api/v1/inference/chat",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": str(10**9)},
    )

    assert client.post("/api/v1/inference/chat", json=too_many_images).status_code == 422
    assert client.post("/api/v1/inference/chat", json=too_long).status_code == 422
    assert huge.status_code == 413


def test_inference_and_model_changes_are_refused_while_a_benchmark_measures(
    client: TestClient, fake_lemonade: FakeLemonade
) -> None:
    client.app.state.benchmarks._starting = True  # type: ignore[attr-defined]

    responses = [
        client.post("/api/v1/inference/chat", json=_chat()),
        client.post("/api/v1/inference/chat/stream", json=_chat()),
        client.post("/api/v1/models/load", json={"model": TEXT_MODEL}),
        client.post("/api/v1/models/unload", json={"model": TEXT_MODEL}),
    ]

    assert [response.status_code for response in responses] == [409] * 4
    assert "benchmark is running" in responses[0].json()["detail"]
    assert not [request for request in fake_lemonade.requests if request[0] == "POST"]


def test_unknown_backend_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/inference/chat", json=_chat(backend="http://evil.example"))

    assert response.status_code == 422
    assert "Unknown backend" in response.json()["detail"]


def test_inference_on_a_model_that_is_not_downloaded_is_a_conflict(
    client: TestClient, fake_lemonade: FakeLemonade
) -> None:
    response = client.post("/api/v1/inference/chat", json=_chat(NOT_DOWNLOADED))

    assert response.status_code == 409
    assert "not downloaded" in response.json()["detail"]
    assert fake_lemonade.posts("/v1/chat/completions") == []


def test_model_details_and_load_unload(client: TestClient) -> None:
    details = client.get(f"/api/v1/models/lemonade/{TEXT_MODEL}").json()
    loaded = client.post("/api/v1/models/load", json={"model": VISION_MODEL})
    unloaded = client.post("/api/v1/models/unload", json={"model": VISION_MODEL})

    assert (details["loaded"], details["quantization"], details["downloaded"]) == (
        True,
        "Q4_0",
        True,
    )
    assert loaded.json()["loaded"] is True
    assert unloaded.json()["loaded"] is False
    assert client.get("/api/v1/models/lemonade/nope").status_code == 404
    assert client.get("/api/v1/models/mock/mock/echo-small").json()["simulated"] is True


def test_loading_a_model_that_is_not_downloaded_does_not_download_it(
    client: TestClient, fake_lemonade: FakeLemonade
) -> None:
    response = client.post("/api/v1/models/load", json={"model": NOT_DOWNLOADED})

    assert response.status_code == 409
    assert fake_lemonade.posts("/v1/load") == []
    assert fake_lemonade.posts("/v1/pull") == []


def test_download_requires_explicit_confirmation(
    client: TestClient, fake_lemonade: FakeLemonade
) -> None:
    refused = client.post("/api/v1/models/download", json={"model": NOT_DOWNLOADED})
    declined = client.post(
        "/api/v1/models/download", json={"model": NOT_DOWNLOADED, "confirm": False}
    )
    assert (refused.status_code, declined.status_code) == (422, 422)
    assert fake_lemonade.posts("/v1/pull") == []

    accepted = client.post(
        "/api/v1/models/download", json={"model": NOT_DOWNLOADED, "confirm": True}
    )

    assert accepted.status_code == 202
    assert len(fake_lemonade.posts("/v1/pull")) == 1
    assert client.get("/api/v1/models/downloads").json()["downloads"][0]["percent"] == 40


def test_telemetry_reports_measurements_and_labels_what_is_unavailable(client: TestClient) -> None:
    body = client.get("/api/v1/telemetry").json()

    assert body["system"]["memory_total_bytes"] > 0
    assert body["system"]["processes"][0]["label"] == "Antar API"
    assert body["loaded_models"] == [{"backend": "lemonade", "model": TEXT_MODEL}]
    assert body["lemonade_stats"]["tokens_per_second"] == 100.0
    assert body["benchmark_running"] is False
    unavailable = {item["metric"] for item in body["system"]["unavailable"]}
    assert "gpu_utilization" in unavailable
    assert all(item["reason"] for item in body["system"]["unavailable"])


def test_settings_expose_inference_limits(client: TestClient) -> None:
    assert client.get("/api/v1/settings").json()["inference"]["max_image_bytes"] == 8 * 1024 * 1024


def _wait_until_finished(client: TestClient) -> dict[str, object]:
    for _ in range(200):
        active = client.get("/api/v1/benchmarks/active").json()["active"]
        if active["status"] != "running":
            return active  # type: ignore[no-any-return]
        time.sleep(0.01)
    raise AssertionError("benchmark did not finish")


def test_benchmark_lifecycle_run_review_and_export(client: TestClient) -> None:
    assert client.get("/api/v1/benchmarks").json() == {"benchmarks": []}
    assert client.get("/api/v1/benchmarks/active").json() == {"active": None}
    workloads = client.get("/api/v1/benchmarks/workloads").json()["workloads"]
    assert {workload["id"] for workload in workloads} >= {"general_qa", "vision_basic"}

    config = {
        "name": "api test",
        "model": {"id": TEXT_MODEL},
        "backend": "lemonade",
        "workloads": ["general_qa", "structured_json"],
        "warmup_runs": 1,
        "measured_runs": 1,
    }
    started = client.post("/api/v1/benchmarks", json=config)
    assert started.status_code == 202
    assert started.json()["active"]["total_requests"] == 9

    finished = _wait_until_finished(client)
    assert (finished["status"], finished["completed_requests"]) == ("completed", 9)

    (summary,) = client.get("/api/v1/benchmarks").json()["benchmarks"]
    report_id = summary["id"]
    assert summary["overall"]["completed"] == 7
    assert summary["overall"]["tokens_per_second_median"] == 100.0

    report = client.get(f"/api/v1/benchmarks/{report_id}").json()
    assert report["backend_version"] == "2026.46.2"
    assert report["model"]["quantization"] == "Q4_0"
    assert report["simulated"] is False
    assert len(report["runs"]) == 9

    exported = client.get(f"/api/v1/benchmarks/{report_id}/export", params={"format": "csv"})
    assert exported.headers["content-type"].startswith("text/csv")
    assert f"{report_id}.csv" in exported.headers["content-disposition"]
    assert len(exported.text.strip().splitlines()) == 10
    as_json = client.get(f"/api/v1/benchmarks/{report_id}/export")
    assert as_json.json()["id"] == report_id

    reviewed = client.patch(
        f"/api/v1/benchmarks/{report_id}/runs/0", json={"score": 5, "notes": "Good."}
    )
    assert reviewed.json()["runs"][0]["manual_score"] == 5
    assert (
        client.patch(f"/api/v1/benchmarks/{report_id}/runs/0", json={"score": 9}).status_code == 422
    )
    assert client.get("/api/v1/benchmarks/unknown-id").status_code == 404


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"workloads": ["nope"]}, 422),
        ({"measured_runs": 0}, 422),
        ({"concurrency": 8}, 422),
        ({"model": {"id": NOT_DOWNLOADED}}, 409),
        ({"model": {"id": "missing"}}, 404),
        ({"workloads": ["vision_basic"]}, 422),
        ({"backend": "amd_cloud"}, 503),
    ],
)
def test_benchmark_start_validation(
    client: TestClient, overrides: dict[str, object], status: int
) -> None:
    config = {
        "name": "bad",
        "model": {"id": TEXT_MODEL},
        "backend": "lemonade",
        "workloads": ["general_qa"],
        **overrides,
    }

    assert client.post("/api/v1/benchmarks", json=config).status_code == status


def test_cancel_without_a_running_benchmark_is_harmless(client: TestClient) -> None:
    assert client.post("/api/v1/benchmarks/active/cancel").json() == {"active": None}
