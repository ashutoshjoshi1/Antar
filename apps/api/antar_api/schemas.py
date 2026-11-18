"""Response models for the HTTP API. Domain types are reused directly where they fit."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from antar.backends.amd_cloud.config import GpuDevice
from antar.backends.amd_cloud.feasibility import FeasibilityRequest
from antar.backends.base import (
    Availability,
    BackendKind,
    BackendStatus,
    Capability,
    DownloadJob,
)
from antar.backends.lemonade.client import LemonadeCloudProvider, LemonadeStats
from antar.benchmarking.runner import BenchmarkProgress
from antar.benchmarking.store import ReportSummary
from antar.benchmarking.workloads import Workload
from antar.comparison.manager import ComparisonProgress
from antar.comparison.report import ComparisonConfig
from antar.comparison.store import ComparisonSummary
from antar.hardware.gpu import GpuSample
from antar.hardware.telemetry import SystemTelemetry
from antar.inference.types import ChatRequest
from antar.modalities.catalog import ModalityInfo
from antar.models.catalog import KnownModel
from antar.models.spec import ModelSpec
from antar.optimization.job import TechniqueApplicability
from antar.orchestration.experiment import ExperimentRecord


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    time: datetime


class BackendsResponse(BaseModel):
    backends: tuple[BackendStatus, ...]


class BackendCapabilities(BaseModel):
    backend: str
    display_name: str
    kind: BackendKind
    availability: Availability
    capabilities: tuple[Capability, ...]


class CapabilitiesResponse(BaseModel):
    modalities: tuple[ModalityInfo, ...]
    techniques: tuple[TechniqueApplicability, ...]
    backends: tuple[BackendCapabilities, ...]


class LemonadeSettingsView(BaseModel):
    base_url: str
    api_key_configured: bool
    timeout_seconds: float


class AmdCloudSettingsView(BaseModel):
    """The configured AMD cloud profile. Key paths and credentials are never returned."""

    name: str
    ssh_host: str
    ssh_user: str | None
    ssh_port: int
    ssh_key_configured: bool
    remote_workdir: str
    rocm_version: str | None
    gpus: tuple[GpuDevice, ...]


class CloudEndpointView(BaseModel):
    """The configured cloud endpoint. The API key is reduced to a boolean."""

    base_url: str
    loopback: bool
    api_key_configured: bool
    trusted_hosts: tuple[str, ...]
    declared_models: tuple[str, ...]
    vllm_image: str | None
    generation_timeout_seconds: float


class CloudCostView(BaseModel):
    hourly_price_usd: float | None
    credit_balance_usd: float | None
    max_experiment_minutes: float


class InferenceLimitsView(BaseModel):
    max_image_bytes: int
    generation_timeout_seconds: float


class StorageSettingsView(BaseModel):
    models_dir: str
    artifacts_dir: str
    training_dir: str
    benchmarks_dir: str
    experiments_dir: str
    comparisons_dir: str


class SettingsResponse(BaseModel):
    config_file: str
    config_file_found: bool
    mock_backend_enabled: bool
    lemonade: LemonadeSettingsView
    amd_cloud: AmdCloudSettingsView | None
    cloud: CloudEndpointView | None
    cloud_cost: CloudCostView
    inference: InferenceLimitsView
    storage: StorageSettingsView


class ExperimentsResponse(BaseModel):
    experiments: tuple[ExperimentRecord, ...]


class ChatBody(ChatRequest):
    """A chat request. The backend is chosen by name; URLs are never accepted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: str = Field(default="lemonade", min_length=1)


class ErrorEvent(BaseModel):
    """Sent on the event stream when generation fails after the stream has started."""

    type: Literal["error"] = "error"
    message: str
    kind: str


class ModelActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: str = Field(default="lemonade", min_length=1)
    model: str = Field(min_length=1)


class DownloadBody(ModelActionBody):
    # Downloads can be several gigabytes, so the caller must opt in explicitly.
    confirm: Literal[True]


class DownloadsResponse(BaseModel):
    downloads: tuple[DownloadJob, ...]


class LoadedModel(BaseModel):
    backend: str
    model: str


class TelemetryResponse(BaseModel):
    system: SystemTelemetry
    loaded_models: tuple[LoadedModel, ...]
    # Lemonade's own counters. They describe the server's latest request and
    # totals since it started, not any particular Antar request.
    lemonade_stats: LemonadeStats | None
    benchmark_running: bool


class WorkloadsResponse(BaseModel):
    workloads: tuple[Workload, ...]


class BenchmarkStateResponse(BaseModel):
    active: BenchmarkProgress | None


class BenchmarkHistoryResponse(BaseModel):
    benchmarks: tuple[ReportSummary, ...]


class ManualEvaluationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=2000)


# The name Antar registers its endpoint under in Lemonade's cloud routing.
LEMONADE_PROVIDER_NAME = "antaramd"


class ConfirmBody(BaseModel):
    """An action that changes something outside Antar, so the caller must opt in."""

    model_config = ConfigDict(extra="forbid")

    confirm: Literal[True]


class CloudStatusResponse(BaseModel):
    endpoint_configured: bool
    base_url: str | None
    loopback: bool | None
    api_key_configured: bool
    ssh_configured: bool
    ssh_host: str | None
    vllm_image: str | None
    status: BackendStatus
    round_trip_ms: float | None = Field(
        description="One GET /health round trip, measured by the Antar API."
    )
    models: tuple[ModelSpec, ...]


class GpuTelemetryResponse(BaseModel):
    ssh_configured: bool
    interval_seconds: float | None
    # Device-level readings. None when there is no SSH host to ask.
    sample: GpuSample | None
    reason: str | None


class CloudCatalogResponse(BaseModel):
    models: tuple[KnownModel, ...]


class FeasibilityBody(FeasibilityRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(min_length=1)


class LemonadeProviderResponse(BaseModel):
    name: str
    lemonade_reachable: bool
    supported: bool | None = Field(description="None when Lemonade could not be asked.")
    provider: LemonadeCloudProvider | None = None
    detail: str | None = None


class ComparisonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: ComparisonConfig
    # A comparison keeps a paid instance busy; the caller must acknowledge that.
    confirm_cloud_usage: Literal[True]


class ComparisonStateResponse(BaseModel):
    active: ComparisonProgress | None


class ComparisonHistoryResponse(BaseModel):
    comparisons: tuple[ComparisonSummary, ...]
