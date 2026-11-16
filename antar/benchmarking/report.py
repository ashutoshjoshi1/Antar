"""The benchmark artifact: everything needed to interpret and reproduce a run."""

import math
import statistics
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from antar.benchmarking.config import BenchmarkConfig
from antar.benchmarking.workloads import Workload
from antar.hardware.profile import HardwareProfile
from antar.hardware.telemetry import Unavailable
from antar.inference.types import InferenceMetrics

SCHEMA_VERSION = 1
ID_PATTERN = r"^[a-z0-9][a-z0-9_\-]{0,63}$"

Phase = Literal["cold", "warmup", "measured"]
ReportStatus = Literal["completed", "cancelled", "failed"]


class RunRecord(BaseModel):
    """One request. Kept individually so aggregates can always be recomputed."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    workload: str
    prompt_id: str
    phase: Phase
    ok: bool
    error: str | None = None
    metrics: InferenceMetrics | None = None
    response: str | None = None
    finish_reason: str | None = None
    json_valid: bool | None = Field(
        default=None, description="Only for workloads that require JSON output."
    )
    # Filled in by a person. Antar computes no quality score for free-text or vision answers.
    manual_score: int | None = Field(default=None, ge=1, le=5)
    manual_notes: str | None = Field(default=None, max_length=2000)


class Aggregate(BaseModel):
    """Statistics over the *measured* runs of one workload, or of all of them."""

    model_config = ConfigDict(frozen=True)

    workload: str = Field(description="A workload id, or 'all'.")
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)
    latency_ms_mean: float | None = None
    latency_ms_median: float | None = None
    latency_ms_p95: float | None = None
    tokens_per_second_mean: float | None = None
    tokens_per_second_median: float | None = None
    first_chunk_ms_median: float | None = None
    output_tokens_mean: float | None = None
    json_valid_rate: float | None = None


class ColdStart(BaseModel):
    model_config = ConfigDict(frozen=True)

    load_time_ms: float = Field(ge=0, description="Time for the backend to load the model.")
    first_request: RunRecord | None = None


class ModelSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    checkpoint: str | None = None
    quantization: str | None = None
    runtime: str | None = None
    size_bytes: int | None = None


class BenchmarkReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    id: str = Field(pattern=ID_PATTERN)
    status: ReportStatus
    simulated: bool = Field(description="True if a mock backend produced the responses.")
    notes: str | None = None
    antar_version: str
    git_commit: str | None = None
    backend: str
    backend_version: str | None = None
    model: ModelSnapshot
    hardware: HardwareProfile
    config: BenchmarkConfig
    workloads: tuple[Workload, ...]
    cold_start: ColdStart | None = None
    runs: tuple[RunRecord, ...]
    aggregates: tuple[Aggregate, ...]
    missing_telemetry: tuple[Unavailable, ...] = ()
    failure: str | None = None
    started_at: datetime
    finished_at: datetime


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Nearest-rank percentile: the smallest value with at least ``fraction`` at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def aggregate(workload: str, runs: Iterable[RunRecord]) -> Aggregate:
    """Summarize measured runs. Cold and warm-up runs are excluded by design."""
    measured = [run for run in runs if run.phase == "measured"]
    succeeded = [run for run in measured if run.ok and run.metrics is not None]
    metrics = [run.metrics for run in succeeded if run.metrics is not None]
    latencies = [item.latency_ms for item in metrics]
    speeds = [item.tokens_per_second for item in metrics if item.tokens_per_second is not None]
    first_chunks = [item.first_chunk_ms for item in metrics if item.first_chunk_ms is not None]
    outputs = [
        float(item.completion_tokens) for item in metrics if item.completion_tokens is not None
    ]
    checked = [run.json_valid for run in succeeded if run.json_valid is not None]
    failed = len(measured) - len(succeeded)
    return Aggregate(
        workload=workload,
        completed=len(succeeded),
        failed=failed,
        error_rate=failed / len(measured) if measured else 0.0,
        latency_ms_mean=_mean(latencies),
        latency_ms_median=_median(latencies),
        latency_ms_p95=percentile(latencies, 0.95),
        tokens_per_second_mean=_mean(speeds),
        tokens_per_second_median=_median(speeds),
        first_chunk_ms_median=_median(first_chunks),
        output_tokens_mean=_mean(outputs),
        json_valid_rate=sum(checked) / len(checked) if checked else None,
    )


def build_aggregates(
    runs: Sequence[RunRecord], workload_ids: Sequence[str]
) -> tuple[Aggregate, ...]:
    per_workload = [
        aggregate(workload_id, (run for run in runs if run.workload == workload_id))
        for workload_id in workload_ids
    ]
    return (*per_workload, aggregate("all", runs))
