"""Benchmark statistics, runner behaviour, persistence, and the job manager."""

import asyncio
import csv
import io
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import ValidationError

from antar.backends.base import BackendKind, BackendStatus, Capability, RuntimeBackend
from antar.backends.mock.backend import MockBackend
from antar.benchmarking.config import BenchmarkConfig
from antar.benchmarking.manager import BenchmarkManager
from antar.benchmarking.report import (
    BenchmarkReport,
    ModelSnapshot,
    Phase,
    RunRecord,
    aggregate,
    percentile,
)
from antar.benchmarking.runner import (
    BenchmarkEnvironment,
    BenchmarkRunner,
    is_valid_json,
    total_requests,
)
from antar.benchmarking.store import CSV_COLUMNS, BenchmarkStore, to_csv
from antar.benchmarking.workloads import WORKLOADS, get_workload, load_image
from antar.core.errors import (
    AntarError,
    BackendRequestError,
    BenchmarkBusyError,
    CapabilityNotSupportedError,
    ExperimentNotFoundError,
    ModelNotDownloadedError,
    ModelNotFoundError,
)
from antar.core.types import Modality
from antar.hardware.detect import detect_local_hardware
from antar.inference.images import validate_image
from antar.inference.types import ChatDone, ChatEvent, ChatRequest, ChatResult, InferenceMetrics
from antar.models.spec import ModelRef, ModelSpec
from tests.conftest import REPO_ROOT


class ScriptedBackend(RuntimeBackend):
    """A backend with controllable timings, failures, and pauses."""

    name: ClassVar[str] = "scripted"
    display_name: ClassVar[str] = "Scripted"
    kind: ClassVar[BackendKind] = BackendKind.LOCAL

    def __init__(self, *, fail_on: frozenset[int] = frozenset(), vision: bool = False) -> None:
        self.calls: list[str] = []
        self.requests: list[ChatRequest] = []
        self.fail_on = fail_on
        self.vision = vision
        self.gate: asyncio.Event | None = None
        self.stream_closed = False
        self.downloaded = True

    async def status(self) -> BackendStatus:
        return BackendStatus.model_validate(
            {
                "name": self.name,
                "display_name": self.display_name,
                "kind": self.kind,
                "availability": "available",
                "detail": "ok",
                "version": "9.9.9",
            }
        )

    def capabilities(self) -> tuple[Capability, ...]:
        return ()

    async def list_models(self) -> tuple[ModelSpec, ...]:
        modalities = (Modality.TEXT, Modality.VISION) if self.vision else (Modality.TEXT,)
        return (
            ModelSpec(
                id="model-a",
                name="model-a",
                backend=self.name,
                modalities=modalities,
                checkpoint="org/model-a:Q4_K_M",
                quantization="Q4_K_M",
                runtime="llamacpp",
                downloaded=self.downloaded,
            ),
        )

    async def load_model(self, model_id: str) -> None:
        self.calls.append(f"load:{model_id}")

    async def unload_model(self, model_id: str) -> None:
        self.calls.append(f"unload:{model_id}")

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        index = len(self.requests)
        self.requests.append(request)
        try:
            if self.gate is not None:
                await self.gate.wait()
            if index in self.fail_on:
                raise BackendRequestError("Lemonade error (HTTP 500): out of memory")
            metrics = InferenceMetrics(
                latency_ms=100.0 * (index + 1),
                first_chunk_ms=10.0,
                completion_tokens=20,
                tokens_per_second=50.0 + index,
            )
            yield ChatDone(
                result=ChatResult(
                    backend=self.name,
                    model=request.model,
                    content='{"ok": true}',
                    finish_reason="stop",
                    metrics=metrics,
                    simulated=False,
                )
            )
        finally:
            self.stream_closed = True


def _config(**overrides: object) -> BenchmarkConfig:
    values: dict[str, object] = {
        "name": "test",
        "model": ModelRef(id="model-a"),
        "backend": "scripted",
        "workloads": ("structured_json",),
        "warmup_runs": 1,
        "measured_runs": 2,
    }
    return BenchmarkConfig.model_validate({**values, **overrides})


def _environment() -> BenchmarkEnvironment:
    return BenchmarkEnvironment(
        hardware=detect_local_hardware(), model=ModelSnapshot(id="model-a"), backend_version="9.9.9"
    )


def _run(backend: RuntimeBackend, config: BenchmarkConfig) -> BenchmarkReport:
    return asyncio.run(BenchmarkRunner(backend, config, _environment()).run("bench-test"))


def _record(
    index: int,
    latency: float,
    *,
    phase: Phase = "measured",
    ok: bool = True,
    tps: float | None = 10,
) -> RunRecord:
    metrics = InferenceMetrics(latency_ms=latency, tokens_per_second=tps) if ok else None
    return RunRecord(
        index=index,
        workload="general_qa",
        prompt_id="p",
        phase=phase,
        ok=ok,
        error=None if ok else "boom",
        metrics=metrics,
    )


# --- statistics


@pytest.mark.parametrize(
    ("values", "fraction", "expected"),
    [
        ([], 0.95, None),
        ([7.0], 0.95, 7.0),
        ([1.0, 2.0, 3.0, 4.0], 0.5, 2.0),
        (list(map(float, range(1, 21))), 0.95, 19.0),
        (list(map(float, range(1, 101))), 0.95, 95.0),
        ([3.0, 1.0, 2.0], 1.0, 3.0),
    ],
)
def test_percentile_uses_nearest_rank(
    values: list[float], fraction: float, expected: float | None
) -> None:
    assert percentile(values, fraction) == expected


def test_aggregate_summarizes_measured_runs_only() -> None:
    runs = [
        _record(0, 9000, phase="cold"),
        _record(1, 5000, phase="warmup"),
        _record(2, 100, tps=10),
        _record(3, 200, tps=20),
        _record(4, 600, tps=30),
    ]

    result = aggregate("general_qa", runs)

    assert result.completed == 3
    assert result.latency_ms_mean == pytest.approx(300)
    assert result.latency_ms_median == 200
    assert result.latency_ms_p95 == 600
    assert result.tokens_per_second_mean == pytest.approx(20)
    assert result.tokens_per_second_median == 20
    assert result.error_rate == 0


def test_aggregate_counts_failures_and_keeps_missing_metrics_unavailable() -> None:
    runs = [_record(0, 100, tps=None), _record(1, 0, ok=False), _record(2, 0, ok=False)]

    result = aggregate("general_qa", runs)

    assert (result.completed, result.failed) == (1, 2)
    assert result.error_rate == pytest.approx(2 / 3)
    assert result.tokens_per_second_mean is None
    assert result.json_valid_rate is None


def test_aggregate_of_no_runs_reports_nothing() -> None:
    result = aggregate("general_qa", [])

    assert result.completed == 0
    assert result.error_rate == 0
    assert result.latency_ms_mean is None


@pytest.mark.parametrize(
    ("text", "valid"),
    [
        ('{"a": 1}', True),
        ('```json\n{"a": 1}\n```', True),
        ("```\n[1, 2]\n```", True),
        ('Here you go: {"a": 1}', False),
        ("", False),
    ],
)
def test_json_validity_check(text: str, valid: bool) -> None:
    assert is_valid_json(text) is valid


# --- workloads and configuration


def test_builtin_workloads_cover_three_text_tasks_and_vision() -> None:
    text = [workload.id for workload in WORKLOADS if workload.modality is Modality.TEXT]
    vision = [workload for workload in WORKLOADS if workload.modality is Modality.VISION]

    assert text[:3] == ["general_qa", "code_generation", "structured_json"]
    assert [workload.id for workload in vision] == ["vision_basic", "vision_reference", "ocr_basic"]
    assert all(prompt.image for workload in vision for prompt in workload.prompts)


def test_every_scored_workload_records_its_license_and_provenance() -> None:
    scored = [workload for workload in WORKLOADS if workload.scored]

    assert {workload.id for workload in scored} == {
        "qa_exact",
        "reasoning_basic",
        "json_schema",
        "code_tests",
        "vision_reference",
        "ocr_basic",
    }
    assert all(workload.license and workload.provenance for workload in scored)
    # A scored workload has a reference for every prompt, so its accuracy covers all of it.
    assert all(prompt.expect for workload in scored for prompt in workload.prompts)


def test_bundled_vision_images_are_valid_pngs() -> None:
    images = {
        prompt.image
        for workload in WORKLOADS
        for prompt in workload.prompts
        if prompt.image is not None
    }
    assert len(images) == 5
    for image in images:
        validate_image(load_image(image), max_bytes=100_000)
    for prompt in get_workload("vision_basic").prompts:
        assert prompt.image is not None
        validate_image(load_image(prompt.image), max_bytes=100_000)


@pytest.mark.parametrize(
    "overrides",
    [
        {"workloads": ("not_a_workload",)},
        {"workloads": ()},
        {"workloads": ("general_qa", "general_qa")},
        {"measured_runs": 0},
        {"concurrency": 4},
        {"temperature": 5},
    ],
)
def test_benchmark_config_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _config(**overrides)


def test_total_requests_counts_warmups_measured_runs_and_cold_start() -> None:
    prompts = len(get_workload("structured_json").prompts)

    assert total_requests(_config()) == 1 + 2 * prompts
    assert total_requests(_config(load_policy="reload")) == 1 + 2 * prompts + 1


# --- runner


def test_runner_separates_warmup_from_measured_runs_and_applies_settings() -> None:
    backend = ScriptedBackend()

    report = _run(backend, _config(max_tokens=64, temperature=0.0, seed=7))

    prompts = len(get_workload("structured_json").prompts)
    assert report.status == "completed"
    assert [run.phase for run in report.runs] == ["warmup"] + ["measured"] * (2 * prompts)
    assert report.cold_start is None
    assert backend.calls == ["load:model-a"]
    settings = backend.requests[0].settings
    assert (settings.max_tokens, settings.temperature, settings.seed) == (64, 0.0, 7)
    assert settings.enable_thinking is False
    overall = report.aggregates[-1]
    assert (overall.workload, overall.completed, overall.json_valid_rate) == ("all", 2 * prompts, 1)
    assert report.backend_version == "9.9.9"


def test_reload_policy_measures_load_time_and_a_separate_cold_request() -> None:
    backend = ScriptedBackend()

    report = _run(backend, _config(load_policy="reload"))

    assert backend.calls == ["unload:model-a", "load:model-a"]
    assert report.cold_start is not None
    assert report.cold_start.load_time_ms >= 0
    assert report.cold_start.first_request is not None
    assert report.cold_start.first_request.phase == "cold"
    # The cold request is the slowest by construction but must not affect the aggregate.
    assert report.runs[0].phase == "cold"
    assert report.aggregates[-1].completed == len(report.runs) - 2


def test_failed_request_is_recorded_and_the_run_continues() -> None:
    report = _run(ScriptedBackend(fail_on=frozenset({1})), _config())

    failed = [run for run in report.runs if not run.ok]
    assert [run.error for run in failed] == ["Lemonade error (HTTP 500): out of memory"]
    assert report.status == "completed"
    assert report.aggregates[-1].failed == 1
    assert report.aggregates[-1].error_rate > 0


def test_load_failure_fails_the_benchmark_with_the_reason() -> None:
    class CannotLoad(ScriptedBackend):
        async def load_model(self, model_id: str) -> None:
            raise BackendRequestError("Lemonade error (HTTP 500): insufficient memory")

    report = _run(CannotLoad(), _config())

    assert report.status == "failed"
    assert report.failure is not None
    assert "insufficient memory" in report.failure
    assert report.runs == ()


def test_vision_workload_sends_the_bundled_image() -> None:
    backend = ScriptedBackend(vision=True)

    report = _run(backend, _config(workloads=("vision_basic",), warmup_runs=0, measured_runs=1))

    assert all(len(request.messages[0].images) == 1 for request in backend.requests)
    assert all(run.json_valid is None and run.manual_score is None for run in report.runs)
    assert report.aggregates[-1].json_valid_rate is None


def test_cancelling_stops_the_in_flight_request_and_keeps_finished_runs() -> None:
    async def scenario() -> tuple[BenchmarkReport, ScriptedBackend]:
        backend = ScriptedBackend()
        runner = BenchmarkRunner(backend, _config(warmup_runs=0), _environment())
        task = asyncio.create_task(runner.run("bench-test"))
        while len(backend.requests) < 2:
            await asyncio.sleep(0)
        backend.gate = asyncio.Event()  # the third request now blocks forever
        while len(backend.requests) < 3:
            await asyncio.sleep(0)
        backend.stream_closed = False
        runner.cancel()
        return await task, backend

    report, backend = asyncio.run(scenario())

    assert report.status == "cancelled"
    assert len(report.runs) == 2
    assert backend.stream_closed is True


def test_mock_benchmark_is_marked_simulated_in_progress_and_report(tmp_path: Path) -> None:
    async def scenario() -> BenchmarkReport:
        store = BenchmarkStore(tmp_path)
        manager = BenchmarkManager([MockBackend()], store)
        progress = await manager.start(
            _config(backend="mock", model=ModelRef(id="mock/echo-small"), workloads=("general_qa",))
        )
        await manager.wait()
        assert manager.progress is not None
        assert manager.progress.status == "completed"
        return store.get(progress.id)

    report = asyncio.run(scenario())

    assert report.simulated is True
    assert report.aggregates[-1].tokens_per_second_mean is None


def test_cancelling_during_model_load_does_not_wait_for_the_load() -> None:
    class SlowLoad(ScriptedBackend):
        async def load_model(self, model_id: str) -> None:
            await asyncio.Event().wait()  # never finishes on its own

    async def scenario() -> BenchmarkReport:
        runner = BenchmarkRunner(SlowLoad(), _config(), _environment())
        task = asyncio.create_task(runner.run("bench-test"))
        await asyncio.sleep(0)
        runner.cancel()
        return await asyncio.wait_for(task, timeout=2)

    report = asyncio.run(scenario())

    assert report.status == "cancelled"
    assert report.runs == ()


def test_unexpected_crash_keeps_the_runs_already_measured() -> None:
    class Crashes(ScriptedBackend):
        async def chat_stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
            if len(self.requests) == 2:
                raise RuntimeError("a bug, not a backend error")
            async for event in super().chat_stream(request):
                yield event

    report = _run(Crashes(), _config())

    assert report.status == "failed"
    assert report.failure is not None
    assert "a bug" not in report.failure
    assert len(report.runs) == 2


# --- manager


def test_two_simultaneous_starts_run_only_one_benchmark(tmp_path: Path) -> None:
    async def scenario() -> tuple[list[object], ScriptedBackend]:
        backend = ScriptedBackend()
        backend.gate = asyncio.Event()
        manager = BenchmarkManager([backend], BenchmarkStore(tmp_path))
        outcomes = await asyncio.gather(
            manager.start(_config()), manager.start(_config()), return_exceptions=True
        )
        manager.cancel()
        await manager.wait()
        return list(outcomes), backend

    outcomes, backend = asyncio.run(scenario())

    assert sum(isinstance(outcome, BenchmarkBusyError) for outcome in outcomes) == 1
    assert backend.calls == ["load:model-a"]


def test_manager_refuses_a_second_benchmark_while_one_runs(tmp_path: Path) -> None:
    async def scenario() -> None:
        backend = ScriptedBackend()
        backend.gate = asyncio.Event()
        manager = BenchmarkManager([backend], BenchmarkStore(tmp_path))
        await manager.start(_config())
        with pytest.raises(BenchmarkBusyError):
            await manager.start(_config())
        assert manager.cancel() is True
        await manager.wait()
        assert manager.progress is not None
        assert manager.progress.status == "cancelled"
        assert manager.cancel() is False

    asyncio.run(scenario())


def test_manager_rejects_models_it_cannot_benchmark(tmp_path: Path) -> None:
    async def start(runtime: ScriptedBackend, **overrides: object) -> None:
        await BenchmarkManager([runtime], BenchmarkStore(tmp_path)).start(_config(**overrides))

    not_downloaded = ScriptedBackend()
    not_downloaded.downloaded = False

    with pytest.raises(ModelNotDownloadedError):
        asyncio.run(start(not_downloaded))
    with pytest.raises(ModelNotFoundError):
        asyncio.run(start(ScriptedBackend(), model=ModelRef(id="missing")))
    with pytest.raises(CapabilityNotSupportedError, match="does not accept images"):
        asyncio.run(start(ScriptedBackend(), workloads=("vision_basic",)))
    with pytest.raises(CapabilityNotSupportedError, match="Unknown backend"):
        asyncio.run(start(ScriptedBackend(), backend="elsewhere"))


def test_manager_records_environment_and_missing_telemetry(tmp_path: Path) -> None:
    async def scenario() -> BenchmarkReport:
        store = BenchmarkStore(tmp_path)
        manager = BenchmarkManager([ScriptedBackend()], store)
        progress = await manager.start(_config())
        await manager.wait()
        return store.get(progress.id)

    report = asyncio.run(scenario())

    assert report.model.quantization == "Q4_K_M"
    assert report.model.checkpoint == "org/model-a:Q4_K_M"
    assert report.hardware.cpu_model
    assert report.antar_version
    assert "peak_memory_per_request" in {item.metric for item in report.missing_telemetry}


# --- persistence


def test_store_round_trips_lists_and_exports(tmp_path: Path) -> None:
    store = BenchmarkStore(tmp_path / "benchmarks")
    report = _run(ScriptedBackend(fail_on=frozenset({2})), _config())

    store.save(report)

    assert store.get(report.id) == report
    (summary,) = store.list()
    assert (summary.id, summary.model, summary.status) == ("bench-test", "model-a", "completed")
    assert summary.overall is not None

    rows = list(csv.DictReader(io.StringIO(to_csv(report))))
    assert len(rows) == len(report.runs)
    assert tuple(rows[0]) == CSV_COLUMNS
    assert rows[0]["phase"] == "warmup"
    failed = next(row for row in rows if row["ok"] == "False")
    assert failed["latency_ms"] == ""  # unavailable, not zero
    assert failed["error"]


def test_manual_evaluation_is_saved_on_the_run(tmp_path: Path) -> None:
    store = BenchmarkStore(tmp_path)
    store.save(_run(ScriptedBackend(), _config()))

    store.set_manual_evaluation("bench-test", 1, score=4, notes="Correct, slightly verbose.")

    run = store.get("bench-test").runs[1]
    assert (run.manual_score, run.manual_notes) == (4, "Correct, slightly verbose.")
    with pytest.raises(ExperimentNotFoundError):
        store.set_manual_evaluation("bench-test", 999, score=1, notes=None)


def test_store_skips_corrupt_reports_and_rejects_unsafe_ids(tmp_path: Path) -> None:
    store = BenchmarkStore(tmp_path)
    store.save(_run(ScriptedBackend(), _config()))
    (tmp_path / "broken.json").write_text("{not json")

    assert [summary.id for summary in store.list()] == ["bench-test"]
    with pytest.raises(AntarError):
        store.get("broken")
    with pytest.raises(ExperimentNotFoundError):
        store.get("../../etc/passwd")


def test_illustrative_fixture_matches_the_schema_and_is_labelled() -> None:
    path = REPO_ROOT / "examples" / "benchmarks" / "illustrative-report.json"

    report = BenchmarkReport.model_validate(json.loads(path.read_text()))

    assert report.simulated is True
    assert report.notes is not None
    assert "ILLUSTRATIVE" in report.notes
    assert report.aggregates[-1].tokens_per_second_mean is None
