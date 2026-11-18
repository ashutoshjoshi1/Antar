"""GPU readings for a machine a backend runs on.

Device-level: they describe a whole GPU, not a model or a request.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from antar.core.types import utc_now
from antar.hardware.telemetry import Unavailable


class GpuReading(BaseModel):
    """One GPU at one moment. ``None`` means the value was not reported."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    name: str | None = None
    memory_total_bytes: int | None = Field(default=None, ge=0)
    memory_used_bytes: int | None = Field(default=None, ge=0)
    utilization_percent: float | None = Field(default=None, ge=0)
    temperature_celsius: float | None = None
    power_watts: float | None = Field(default=None, ge=0)


class GpuSample(BaseModel):
    model_config = ConfigDict(frozen=True)

    collected_at: datetime = Field(default_factory=utc_now)
    gpus: tuple[GpuReading, ...] = ()
    driver_version: str | None = None
    rocm_version: str | None = None
    amd_smi_version: str | None = None
    unavailable: tuple[Unavailable, ...] = ()
