"""Model specification: how Antar describes a model regardless of where it runs."""

from pydantic import BaseModel, ConfigDict, Field

from antar.core.types import Modality, Task


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
    labels: tuple[str, ...] = Field(default=(), description="Backend-provided tags, verbatim.")
    simulated: bool = Field(
        default=False, description="True for mock models that produce no real inference."
    )
