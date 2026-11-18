"""Comparison Lab: two real benchmark runs lined up, with nothing invented for a missing side."""

import asyncio
import csv
import io
from pathlib import Path

import httpx
import pytest

from antar.backends.amd_cloud.amd_smi import GPU_COMMAND
from antar.backends.amd_cloud.config import (
    AmdCloudProfile,
    CloudCostSettings,
    CloudEndpointSettings,
)
from antar.backends.amd_cloud.cost import CloudSession
from antar.backends.base import RuntimeBackend
from antar.backends.registry import build_backends
from antar.benchmarking.manager import BenchmarkManager, JobSlot
from antar.benchmarking.report import decode_tokens_per_second
from antar.benchmarking.store import BenchmarkStore
from antar.comparison.export import to_csv, to_markdown
from antar.comparison.manager import ComparisonManager
from antar.comparison.report import (
    ComparisonConfig,
    ComparisonReport,
    ComparisonRow,
    summarize_gpu,
)
from antar.comparison.store import ComparisonStore
from antar.config.settings import Settings
from antar.core.errors import BenchmarkBusyError, CapabilityNotSupportedError
from antar.hardware.gpu import GpuReading, GpuSample
from antar.inference.types import InferenceMetrics
from tests.conftest import CLOUD_URL, FakeLemonade, FakeRunner, FakeVllm
from tests.unit.test_cloud_host import _amd_smi

LOCAL = {"backend": "lemonade", "model": {"id": "Qwen3-0.6B-GGUF"}}
CLOUD = {"backend": "amd_cloud", "model": {"id": "Qwen/Qwen3-8B"}}


def _config(**overrides: object) -> ComparisonConfig:
    values: dict[str, object] = {
        "name": "tiny vs 8B",
        "local": LOCAL,
        "cloud": CLOUD,
        "workloads": ["reasoning_basic"],
        "warmup_runs": 1,
        "measured_runs": 1,
    }
    return ComparisonConfig.model_validate({**values, **overrides})


class Lab:
    """A comparison manager wired to stand-in Lemonade, vLLM, and SSH."""

    def __init__(self, settings: Settings, tmp_path: Path, *, price: float | None = 6.0) -> None:
        self.lemonade = FakeLemonade()
        self.vllm = FakeVllm()
        self.runner = FakeRunner({GPU_COMMAND: _amd_smi()})
        configured = settings.model_copy(
            update={
                "cloud": CloudEndpointSettings.model_validate({"base_url": CLOUD_URL}),
                "amd_cloud": AmdCloudProfile(name="lab", ssh_host="amd-box"),
            }
        )
        self.backends: tuple[RuntimeBackend, ...] = build_backends(
            configured,
            lemonade_transport=httpx.MockTransport(self.lemonade),
            cloud_transport=httpx.MockTransport(self.vllm),
            cloud_runner=self.runner,
        )
        self.slot = JobSlot()
        self.benchmarks = BenchmarkManager(
            self.backends, BenchmarkStore(tmp_path / "benchmarks"), self.slot
        )
        self.store = ComparisonStore(tmp_path / "comparisons")
        self.manager = ComparisonManager(
            self.backends,
            self.benchmarks,
            self.store,
            self.slot,
            cost=CloudCostSettings(),
            session=lambda: CloudSession(hourly_price_usd=price),
            vllm_image="vllm/vllm-openai-rocm:v0.34.0-rocm100",
            gpu_interval_seconds=0.01,
        )

    async def run(self, config: ComparisonConfig) -> ComparisonReport:
        progress = await self.manager.start(config)
        await self.manager.wait()
        return self.store.get(progress.id)


@pytest.fixture
def lab(settings: Settings, tmp_path: Path) -> Lab:
    return Lab(settings, tmp_path)


def _row(report: ComparisonReport, metric: str, workload: str = "all") -> ComparisonRow:
    return next(row for row in report.rows if row.metric == metric and row.workload == workload)


def test_both_sides_run_the_same_prompts_and_are_recorded_separately(lab: Lab) -> None:
    report = asyncio.run(lab.run(_config()))

    assert report.status == "completed"
    assert report.simulated is False
    assert report.local is not None
    assert report.cloud is not None
    assert (report.local.execution, report.cloud.execution) == ("local", "cloud")
    assert [run.prompt_id for run in report.local.runs] == [
        run.prompt_id for run in report.cloud.runs
    ]
    # 1 warm-up + 6 prompts per side, each a real request to its own server.
    assert len(lab.lemonade.posts("/v1/chat/completions")) == 7
    assert len(lab.vllm.chats()) == 7
    assert lab.slot.busy is False


def test_metrics_a_backend_does_not_report_stay_unavailable_on_that_side(lab: Lab) -> None:
    report = asyncio.run(lab.run(_config()))

    backend_speed = _row(report, "tokens_per_second_median")
    assert backend_speed.measured_by == "backend"
    assert backend_speed.local == 100.0
    assert backend_speed.cloud is None
    latency = _row(report, "latency_ms_median")
    assert latency.scope == "end_to_end"
    assert latency.measured_by == "antar"
    assert latency.local is not None
    assert latency.cloud is not None
    assert _row(report, "prompt_processing_ms_median").cloud is None
    assert _row(report, "first_request_ms").cloud is not None


def test_quality_scores_come_from_the_reference_answers(lab: Lab) -> None:
    report = asyncio.run(lab.run(_config()))

    # The stand-in servers answer "Hello" and "42"; only the sequence question's answer is 42.
    accuracy = _row(report, "accuracy", "reasoning_basic")
    assert accuracy.measured_by == "scorer"
    assert accuracy.local == 0.0
    assert accuracy.cloud == pytest.approx(1 / 6)
    assert report.cloud is not None
    scored = {run.prompt_id: run.score for run in report.cloud.runs if run.phase == "measured"}
    assert scored["sequence"] == 1.0
    assert scored["multiply"] == 0.0


def test_the_cloud_environment_and_usage_are_recorded(lab: Lab) -> None:
    report = asyncio.run(lab.run(_config()))

    assert report.gpu is not None
    assert report.gpu.gpu_count == 2
    assert report.gpu.gpu_names == ("AMD Instinct MI300X",)
    assert report.gpu.memory_used_peak_bytes == 2 * 70000 * 1000**2
    assert (report.gpu.driver_version, report.gpu.rocm_version) == ("6.12.12", "7.1.0")
    assert report.cloud is not None
    assert report.cloud.remote_gpus is not None
    assert report.cloud.backend_version == "0.34.0"
    assert report.cloud.model.parameter_count == 8_190_735_360
    assert report.vllm_image == "vllm/vllm-openai-rocm:v0.34.0-rocm100"
    assert report.lemonade_version == "2026.46.2"
    assert report.transport is not None
    assert len(report.transport.samples_ms) == 5
    assert report.usage.cloud_seconds is not None
    assert report.usage.estimated_cost_usd == pytest.approx(report.usage.cloud_seconds / 3600 * 6)
    assert any("Not a hardware-normalized comparison" in caveat for caveat in report.caveats)


def test_without_a_price_no_cost_is_estimated(settings: Settings, tmp_path: Path) -> None:
    report = asyncio.run(Lab(settings, tmp_path, price=None).run(_config()))

    assert report.usage.cloud_seconds is not None
    assert report.usage.estimated_cost_usd is None


def test_the_sides_cannot_be_swapped_or_doubled(lab: Lab) -> None:
    with pytest.raises(CapabilityNotSupportedError, match="runs on this machine"):
        asyncio.run(lab.manager.start(_config(cloud=LOCAL)))
    with pytest.raises(CapabilityNotSupportedError, match="runs in the cloud"):
        asyncio.run(lab.manager.start(_config(local=CLOUD)))

    assert lab.slot.busy is False
    assert lab.vllm.chats() == []


def test_a_failed_local_side_spends_no_cloud_time(lab: Lab) -> None:
    lab.lemonade.overrides[("POST", "/v1/load")] = httpx.Response(
        500, json={"error": {"message": "out of memory"}}
    )

    report = asyncio.run(lab.run(_config()))

    assert report.status == "failed"
    assert report.failure is not None
    assert "local side failed" in report.failure
    assert report.cloud is None
    assert lab.vllm.chats() == []
    assert report.usage.cloud_seconds is None


def test_only_one_measuring_job_runs_at_a_time(lab: Lab) -> None:
    async def scenario() -> None:
        await lab.manager.start(_config())
        with pytest.raises(BenchmarkBusyError, match="comparison is already running"):
            await lab.manager.start(_config())
        with pytest.raises(BenchmarkBusyError):
            await lab.benchmarks.start(_config().benchmark_config("local"))
        await lab.manager.wait()

    asyncio.run(scenario())

    assert lab.slot.busy is False


def test_cancelling_saves_what_finished_and_says_why(lab: Lab) -> None:
    async def scenario() -> ComparisonReport:
        progress = await lab.manager.start(_config(measured_runs=50))
        while not lab.vllm.chats():
            await asyncio.sleep(0)
        assert lab.manager.cancel() is True
        await lab.manager.wait()
        return lab.store.get(progress.id)

    report = asyncio.run(scenario())

    assert report.status == "cancelled"
    assert report.failure == "Cancelled by the user."
    assert report.local is not None
    assert report.local.status == "completed"
    assert report.cloud is not None
    assert len(report.cloud.runs) < 301
    assert lab.manager.progress is not None
    assert lab.manager.progress.status == "cancelled"


def test_the_time_budget_stops_a_comparison(lab: Lab) -> None:
    report = asyncio.run(lab.run(_config(measured_runs=100, time_budget_minutes=0.0005)))

    assert report.status == "cancelled"
    assert report.failure is not None
    assert "time budget" in report.failure


def test_csv_export_has_one_row_per_request_with_blanks_for_unavailable(lab: Lab) -> None:
    report = asyncio.run(lab.run(_config()))

    rows = list(csv.DictReader(io.StringIO(to_csv(report))))

    assert len(rows) == 14
    assert {row["side"] for row in rows} == {"local", "cloud"}
    cloud = next(row for row in rows if row["side"] == "cloud" and row["phase"] == "measured")
    assert cloud["model"] == "Qwen/Qwen3-8B"
    assert cloud["tokens_per_second"] == ""
    assert cloud["completion_tokens"] == "4"
    assert cloud["score"] in ("0.0", "1.0")


def test_markdown_report_states_method_limits_and_unavailable_values(lab: Lab) -> None:
    report = asyncio.run(lab.run(_config()))

    markdown = to_markdown(report)

    assert markdown.startswith("# tiny vs 8B")
    assert "not a hardware-normalized comparison" in markdown
    assert "| Tokens per second, backend-reported, median | 100.0 tok/s | n/a |" in markdown
    assert "## Methodology" in markdown
    assert "`reasoning_basic` v1" in markdown
    assert "## Limitations" in markdown
    assert "xychart-beta" in markdown
    assert "AMD Instinct MI300X" in markdown
    assert "Simulated" not in markdown


def test_a_mock_comparison_is_labelled_simulated(lab: Lab) -> None:
    mock = {
        "local": {"backend": "mock", "model": {"id": "mock/echo-small"}},
        "cloud": {"backend": "mock", "model": {"id": "mock/echo-large"}},
    }

    report = asyncio.run(lab.run(_config(workloads=["general_qa"], **mock)))

    assert report.status == "completed"
    assert report.simulated is True
    assert "**Simulated.**" in to_markdown(report)
    # No cloud was involved, so nothing about a cloud is reported, even though one is configured.
    assert report.transport is None
    assert report.gpu is None
    assert report.usage.cloud_seconds is None
    assert report.usage.estimated_cost_usd is None
    assert lab.runner.commands == []
    assert lab.store.list()[0].simulated is True


def test_gpu_summary_never_sums_a_partial_reading() -> None:
    def sample(used: tuple[int | None, int | None], utilization: float | None) -> GpuSample:
        return GpuSample(
            gpus=tuple(
                GpuReading(index=index, memory_used_bytes=value, utilization_percent=utilization)
                for index, value in enumerate(used)
            )
        )

    summary = summarize_gpu([sample((10, 20), 50.0), sample((40, None), None)], 5.0)

    assert summary is not None
    assert summary.samples == 2
    assert summary.memory_used_peak_bytes == 30
    assert summary.utilization_mean_percent == 50.0
    assert summary.memory_total_bytes is None
    assert summary.power_peak_watts is None
    assert summarize_gpu([], 5.0) is None


def test_decode_rate_uses_only_antars_own_clock() -> None:
    metrics = InferenceMetrics(latency_ms=2500, first_chunk_ms=500, completion_tokens=100)

    assert decode_tokens_per_second(metrics) == pytest.approx(50.0)
    assert decode_tokens_per_second(InferenceMetrics(latency_ms=10, completion_tokens=5)) is None
    single = InferenceMetrics(latency_ms=10, first_chunk_ms=10, completion_tokens=1)
    assert decode_tokens_per_second(single) is None
