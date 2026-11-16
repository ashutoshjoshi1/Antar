"""Hardware profile: the typed description of a machine Antar can target."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AcceleratorKind(StrEnum):
    APPLE_GPU = "apple_gpu"
    AMD_GPU = "amd_gpu"
    NVIDIA_GPU = "nvidia_gpu"
    NPU = "npu"
    OTHER = "other"


class Accelerator(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    kind: AcceleratorKind
    vendor: str | None = None
    memory_bytes: int | None = Field(
        default=None, ge=0, description="Dedicated memory. None when unknown or shared."
    )
    shares_system_memory: bool = Field(
        default=False, description="True for unified-memory designs such as Apple Silicon."
    )
    cores: int | None = Field(default=None, ge=0)


class RuntimeSupport(BaseModel):
    """Whether a compute runtime looks usable on this machine, and how we know."""

    model_config = ConfigDict(frozen=True)

    name: str
    available: bool
    version: str | None = None
    detail: str


class HardwareProfile(BaseModel):
    """A snapshot of a machine. Detected locally, or declared for remote hosts."""

    model_config = ConfigDict(frozen=True)

    hostname: str
    os: str
    os_version: str
    architecture: str
    python_version: str
    cpu_model: str
    cpu_physical_cores: int | None = None
    cpu_logical_cores: int | None = None
    memory_total_bytes: int = Field(ge=0)
    memory_available_bytes: int = Field(ge=0)
    disk_total_bytes: int = Field(ge=0)
    disk_free_bytes: int = Field(ge=0)
    accelerators: tuple[Accelerator, ...] = ()
    runtimes: tuple[RuntimeSupport, ...] = ()
