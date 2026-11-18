"""Model specification: how Antar describes a model regardless of where it runs."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from antar.core.types import Modality, Task


class ExecutionLocation(StrEnum):
    """Where a model's computation actually happens."""

    LOCAL = "local"
    CLOUD = "cloud"
    MOCK = "mock"


class ModelState(StrEnum):
    """How far a model is from answering a request, as far as the backend reports.

    ``CONFIGURED``  Declared in Antar's configuration or catalog; the backend has not reported it.
    ``DISCOVERED``  Listed by the backend, but its weights are not on that backend.
    ``INSTALLED``   Weights are present on the backend; the model is not in memory.
    ``LOADED``      In memory and able to answer requests now.
    """

    CONFIGURED = "configured"
    DISCOVERED = "discovered"
    INSTALLED = "installed"
    LOADED = "loaded"


class ModelRef(BaseModel):
    """A pinned reference to a model, used wherever reproducibility matters."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, description="Model identifier, e.g. a Hugging Face repo id.")
    revision: str | None = Field(
        default=None, description="Commit hash, tag, or version. Pin this for reproducible runs."
    )


class ModelSpec(BaseModel):
    """A model as reported by a backend or declared in configuration.

    Optional fields are ``None`` when the source does not state them; Antar does
    not guess sizes, licenses, or capabilities.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1, description="Human-readable name.")
    backend: str = Field(description="Name of the backend that reported this model.")
    modalities: tuple[Modality, ...] = Field(
        default=(), description="Empty when the backend does not report enough to classify."
    )
    tasks: tuple[Task, ...] = ()
    revision: str | None = None
    checkpoint: str | None = Field(
        default=None, description="Upstream source of the weights, e.g. a Hugging Face repo."
    )
    runtime: str | None = Field(
        default=None, description="Inference engine or recipe used by the backend."
    )
    size_bytes: int | None = Field(default=None, ge=0)
    license: str | None = None
    downloaded: bool | None = Field(
        default=None, description="Whether weights are present on the backend, if reported."
    )
    loaded: bool | None = Field(
        default=None, description="Whether the model is in memory right now, if reported."
    )
    quantization: str | None = Field(
        default=None, description="Quantization variant or weight precision, e.g. Q4_K_M or BF16."
    )
    context_length: int | None = Field(default=None, ge=0)
    labels: tuple[str, ...] = Field(default=(), description="Backend-provided tags, verbatim.")
    simulated: bool = Field(
        default=False, description="True for mock models that produce no real inference."
    )
    location: ExecutionLocation | None = Field(
        default=None, description="Where inference runs. None when the backend did not say."
    )
    provider: str | None = Field(
        default=None, description="Who serves the model, e.g. 'lemonade' or 'vllm'."
    )
    state: ModelState | None = None
    family: str | None = None
    parameter_count: int | None = Field(
        default=None, ge=0, description="From the model's published metadata, never estimated."
    )
