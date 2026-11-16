"""Deployment manifest: the reproducible description of a chosen configuration."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from antar.core.types import Modality, Task, utc_now
from antar.models.spec import ModelRef


class RoutingPreference(StrEnum):
    LOCAL_ONLY = "local_only"
    LOCAL_FIRST = "local_first"
    CLOUD_FIRST = "cloud_first"
    CLOUD_ONLY = "cloud_only"


class RoutingPolicy(BaseModel):
    """Measurable conditions for choosing between local and cloud execution."""

    model_config = ConfigDict(frozen=True)

    preference: RoutingPreference = RoutingPreference.LOCAL_FIRST
    local_backend: str | None = None
    cloud_backend: str | None = None
    max_local_latency_ms: float | None = Field(default=None, gt=0)
    max_local_memory_gb: float | None = Field(default=None, gt=0)


class ArtifactRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str = Field(min_length=1, description="e.g. 'weights', 'adapter', 'report'.")
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class DeploymentManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    model: ModelRef
    modality: Modality
    task: Task
    backend: str
    runtime_options: dict[str, JsonValue] = Field(default_factory=dict)
    routing: RoutingPolicy = RoutingPolicy()
    experiment_id: str | None = Field(
        default=None, description="The experiment whose results justify this configuration."
    )
    artifacts: tuple[ArtifactRef, ...] = ()
    created_at: datetime = Field(default_factory=utc_now)
