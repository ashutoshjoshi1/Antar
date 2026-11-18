"""The comparison artifact: one local run and one cloud run of the same workloads.

A comparison answers "what does a user get from each place", not "which
hardware is faster". The two sides differ in model, precision, hardware, and
network path at once, so nothing here is hardware-normalized and the report
says so wherever it is rendered.
"""

import statistics
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from antar.benchmarking.config import BenchmarkConfig
from antar.benchmarking.report import ID_PATTERN, Aggregate, BenchmarkReport, RunRecord
from antar.benchmarking.workloads import get_workload
from antar.core.errors import CapabilityNotSupportedError
from antar.hardware.gpu import GpuSample
from antar.hardware.telemetry import Unavailable
from antar.inference.types import InferenceMetrics
from antar.models.spec import ModelRef

SCHEMA_VERSION = 1

Side = Literal["local", "cloud"]
ComparisonStatus = Literal["completed", "cancelled", "failed"]
# Who took the measurement. Shown beside every number.
MeasuredBy = Literal["antar", "backend", "scorer"]
# "end_to_end": what a user waits for, transport included. "model": inference only.
Scope = Literal["end_to_end", "model", "quality", "reliability"]

CAVEATS: tuple[str, ...] = (
    "Not a hardware-normalized comparison. The two sides differ in model size, weight "
    "precision, hardware, and network path at the same time.",
    "End-to-end times are measured by the Antar API and include the path to the backend: "
    "loopback for the local side, an SSH tunnel for the cloud side.",
    "Backend-reported timings exist only where the backend reports them per response. "
    "vLLM reports token counts but no per-response timings.",
    "Statistics cover measured requests only. Warm-up requests are excluded and the first "
    "request of each side is shown separately.",
    "Automatic scores compare a response with a reference by a fixed rule. They are not a "
    "general judgement of quality.",
    "GPU readings are device-level, for the whole GPU, sampled at intervals during the "
    "cloud run. They are not per-model or per-request figures.",
)


class ComparisonTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    backend: str = Field(min_length=1)
    model: ModelRef


class ComparisonConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    local: ComparisonTarget
    cloud: ComparisonTarget
    workloads: tuple[str, ...] = Field(min_length=1)
    warmup_runs: int = Field(default=1, ge=0, le=20)
    measured_runs: int = Field(default=3, ge=1, le=100)
    max_tokens: int = Field(default=256, ge=1, le=16384)
    temperature: float = Field(default=0.0, ge=0, le=2)
    seed: int | None = Field(default=42, ge=0)
    enable_thinking: bool | None = False
    allow_code_execution: bool = False
    time_budget_minutes: float | None = Field(
        default=None, gt=0, le=24 * 60, description="Defaults to the configured experiment limit."
    )

    @field_validator("workloads")
    @classmethod
    def _known_unique_workloads(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for workload_id in value:
            try:
                get_workload(workload_id)
            except CapabilityNotSupportedError as exc:
                raise ValueError(str(exc)) from exc
        if len(set(value)) != len(value):
            raise ValueError("workloads must not repeat")
        return value

    def benchmark_config(self, side: Side) -> BenchmarkConfig:
        """The single-backend run for one side. Both sides share every setting but the model."""
        target = self.local if side == "local" else self.cloud
        return BenchmarkConfig(
            name=f"{self.name} ({side})",
            model=target.model,
            backend=target.backend,
            workloads=self.workloads,
            warmup_runs=self.warmup_runs,
            measured_runs=self.measured_runs,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            seed=self.seed,
            enable_thinking=self.enable_thinking,
            allow_code_execution=self.allow_code_execution,
            # Confirmed once for the comparison as a whole, at the API boundary.
            confirm_cloud_usage=True,
        )


class TransportMeasurement(BaseModel):
    """Round trips of a tiny health request: the cost of the path, with no inference in it."""

    model_config = ConfigDict(frozen=True)

    samples_ms: tuple[float, ...]
    median_ms: float | None
    note: str


class GpuUsageSummary(BaseModel):
    """Device-level readings taken while the cloud side ran."""

    model_config = ConfigDict(frozen=True)

    samples: int = Field(ge=0)
    interval_seconds: float | None = None
    gpu_count: int | None = None
    gpu_names: tuple[str, ...] = ()
    memory_total_bytes: int | None = None
    memory_used_peak_bytes: int | None = None
    utilization_mean_percent: float | None = None
    utilization_peak_percent: float | None = None
    power_peak_watts: float | None = None
    driver_version: str | None = None
    rocm_version: str | None = None
    unavailable: tuple[Unavailable, ...] = ()


class CloudUsage(BaseModel):
    """Time this comparison kept the cloud side busy, and what that costs at the entered price."""

    model_config = ConfigDict(frozen=True)

    cloud_seconds: float | None = Field(default=None, ge=0)
    hourly_price_usd: float | None = None
    estimated_cost_usd: float | None = None
    note: str = (
        "Estimated from this run's duration and the hourly price entered by the operator. The "
        "instance bills for all the time it exists, not only while Antar uses it."
    )


class ComparisonRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    workload: str = Field(description="A workload id, or 'all'.")
    metric: str
    label: str
    unit: str | None = None
    scope: Scope
    measured_by: MeasuredBy
    local: float | None = Field(default=None, description="None: not available.")
    cloud: float | None = Field(default=None, description="None: not available.")


class ComparisonReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    id: str = Field(pattern=ID_PATTERN)
    status: ComparisonStatus
    simulated: bool = Field(description="True if either side was a mock backend.")
    antar_version: str
    git_commit: str | None = None
    config: ComparisonConfig
    local: BenchmarkReport | None = None
    cloud: BenchmarkReport | None = None
    rows: tuple[ComparisonRow, ...] = ()
    transport: TransportMeasurement | None = None
    gpu: GpuUsageSummary | None = None
    usage: CloudUsage = CloudUsage()
    vllm_image: str | None = Field(
        default=None, description="Container image as declared in the configuration."
    )
    lemonade_version: str | None = None
    caveats: tuple[str, ...] = CAVEATS
    failure: str | None = None
    started_at: datetime
    finished_at: datetime


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _measured_median(
    runs: Sequence[RunRecord], workload: str, pick: Callable[[InferenceMetrics], float | None]
) -> float | None:
    values = [
        value
        for run in runs
        if run.phase == "measured"
        and run.ok
        and run.metrics is not None
        and workload in ("all", run.workload)
        and (value := pick(run.metrics)) is not None
    ]
    return _median(values)


def _first_request_ms(report: BenchmarkReport | None) -> float | None:
    """Latency of the very first request a side served in this run, warm-up or not."""
    if report is None or not report.runs:
        return None
    first = report.runs[0]
    return first.metrics.latency_ms if first.ok and first.metrics else None


def _aggregate(report: BenchmarkReport | None, workload: str) -> Aggregate | None:
    if report is None:
        return None
    return next((item for item in report.aggregates if item.workload == workload), None)


_AGGREGATE_ROWS: tuple[tuple[str, str, str | None, Scope, MeasuredBy], ...] = (
    ("latency_ms_median", "End-to-end latency, median", "ms", "end_to_end", "antar"),
    ("latency_ms_p95", "End-to-end latency, p95", "ms", "end_to_end", "antar"),
    ("first_chunk_ms_median", "Time to first token, median", "ms", "end_to_end", "antar"),
    (
        "decode_tokens_per_second_median",
        "Tokens per second after the first token, median",
        "tok/s",
        "end_to_end",
        "antar",
    ),
    (
        "tokens_per_second_median",
        "Tokens per second, backend-reported, median",
        "tok/s",
        "model",
        "backend",
    ),
    ("output_tokens_mean", "Output tokens, mean", "tokens", "model", "backend"),
    ("error_rate", "Error rate", "ratio", "reliability", "antar"),
    ("accuracy", "Automatic score, mean", "ratio", "quality", "scorer"),
    ("json_valid_rate", "Valid JSON rate", "ratio", "quality", "scorer"),
)

_RUN_ROWS: tuple[tuple[str, str, Callable[[InferenceMetrics], float | None]], ...] = (
    (
        "prompt_processing_ms_median",
        "Prompt processing, backend-reported, median",
        lambda metrics: metrics.prompt_processing_ms,
    ),
    (
        "generation_ms_median",
        "Generation time, backend-reported, median",
        lambda metrics: metrics.generation_ms,
    ),
    (
        "input_tokens_median",
        "Input tokens, median",
        lambda metrics: float(metrics.prompt_tokens) if metrics.prompt_tokens is not None else None,
    ),
)


def build_rows(
    local: BenchmarkReport | None, cloud: BenchmarkReport | None, workloads: Sequence[str]
) -> tuple[ComparisonRow, ...]:
    """Line the two sides up metric by metric. A side that has no value stays ``None``."""
    rows: list[ComparisonRow] = []
    for workload in ("all", *workloads):
        mine, theirs = _aggregate(local, workload), _aggregate(cloud, workload)
        rows.extend(
            ComparisonRow(
                workload=workload,
                metric=metric,
                label=label,
                unit=unit,
                scope=scope,
                measured_by=measured_by,
                local=getattr(mine, metric) if mine and mine.completed + mine.failed else None,
                cloud=getattr(theirs, metric)
                if theirs and theirs.completed + theirs.failed
                else None,
            )
            for metric, label, unit, scope, measured_by in _AGGREGATE_ROWS
        )
        rows.extend(
            ComparisonRow(
                workload=workload,
                metric=metric,
                label=label,
                unit="tokens" if metric.startswith("input") else "ms",
                scope="model",
                measured_by="backend",
                local=_measured_median(local.runs, workload, pick) if local else None,
                cloud=_measured_median(cloud.runs, workload, pick) if cloud else None,
            )
            for metric, label, pick in _RUN_ROWS
        )
    rows.append(
        ComparisonRow(
            workload="all",
            metric="first_request_ms",
            label="First request of the run (not in the statistics)",
            unit="ms",
            scope="end_to_end",
            measured_by="antar",
            local=_first_request_ms(local),
            cloud=_first_request_ms(cloud),
        )
    )
    return tuple(rows)


def _complete_sum(values: Sequence[float | None]) -> float | None:
    """The sum across GPUs, or None unless every GPU reported the value."""
    present = [value for value in values if value is not None]
    return sum(present) if present and len(present) == len(values) else None


def summarize_gpu(
    samples: Sequence[GpuSample], interval_seconds: float | None
) -> GpuUsageSummary | None:
    """Reduce the samples of a run. Values no sample carried stay ``None``."""
    if not samples:
        return None
    latest = samples[-1]
    used = [
        total
        for sample in samples
        if (total := _complete_sum([gpu.memory_used_bytes for gpu in sample.gpus])) is not None
    ]
    power = [
        total
        for sample in samples
        if (total := _complete_sum([gpu.power_watts for gpu in sample.gpus])) is not None
    ]
    utilization = [
        gpu.utilization_percent
        for sample in samples
        for gpu in sample.gpus
        if gpu.utilization_percent is not None
    ]
    memory_total = _complete_sum([gpu.memory_total_bytes for gpu in latest.gpus])
    return GpuUsageSummary(
        samples=len(samples),
        interval_seconds=interval_seconds,
        gpu_count=len(latest.gpus) or None,
        gpu_names=tuple(dict.fromkeys(gpu.name for gpu in latest.gpus if gpu.name)),
        memory_total_bytes=round(memory_total) if memory_total is not None else None,
        memory_used_peak_bytes=round(max(used)) if used else None,
        utilization_mean_percent=statistics.fmean(utilization) if utilization else None,
        utilization_peak_percent=max(utilization) if utilization else None,
        power_peak_watts=max(power) if power else None,
        driver_version=latest.driver_version,
        rocm_version=latest.rocm_version,
        unavailable=latest.unavailable,
    )
