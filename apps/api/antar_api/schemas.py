"""Response models for the HTTP API. Domain types are reused directly where they fit."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from antar.backends.amd_cloud.config import GpuDevice
from antar.backends.base import Availability, BackendKind, BackendStatus, Capability
from antar.modalities.catalog import ModalityInfo
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
    ssh_user: str
    ssh_port: int
    ssh_key_configured: bool
    remote_workdir: str
    rocm_version: str | None
    gpus: tuple[GpuDevice, ...]


class StorageSettingsView(BaseModel):
    models_dir: str
    artifacts_dir: str
    training_dir: str
    benchmarks_dir: str
    experiments_dir: str


class SettingsResponse(BaseModel):
    config_file: str
    config_file_found: bool
    mock_backend_enabled: bool
    lemonade: LemonadeSettingsView
    amd_cloud: AmdCloudSettingsView | None
    storage: StorageSettingsView


class ExperimentsResponse(BaseModel):
    experiments: tuple[ExperimentRecord, ...]
