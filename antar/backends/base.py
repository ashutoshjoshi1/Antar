"""The runtime backend contract.

A backend is anything that can host models: a local server, a remote GPU host,
or a mock. Every backend must be able to say whether it is reachable, what it
supports, and which models it has. Inference methods are opt-in: the default
implementation refuses, so a backend can never appear to support something it
has not implemented.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from antar.core.errors import CapabilityNotSupportedError
from antar.core.types import Modality, Task, utc_now
from antar.models.spec import ModelSpec


class BackendKind(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"
    MOCK = "mock"


class Availability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"
    NOT_IMPLEMENTED = "not_implemented"


class SupportLevel(StrEnum):
    """How far support for a capability actually goes.

    ``SUPPORTED``     Antar can execute this through the backend today.
    ``DOCUMENTED``    The backend documents it, but Antar's adapter does not call it yet.
    ``PLANNED``       On the roadmap; nothing is wired up.
    ``UNSUPPORTED``   Not offered by the backend.
    """

    SUPPORTED = "supported"
    DOCUMENTED = "documented"
    PLANNED = "planned"
    UNSUPPORTED = "unsupported"


class Capability(BaseModel):
    model_config = ConfigDict(frozen=True)

    modality: Modality
    task: Task | None = Field(default=None, description="None means the modality as a whole.")
    support: SupportLevel
    note: str | None = None


class BackendStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    display_name: str
    kind: BackendKind
    availability: Availability
    detail: str
    endpoint: str | None = None
    version: str | None = None
    checked_at: datetime = Field(default_factory=utc_now)


class TextGenerationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    max_tokens: int = Field(default=128, ge=1, le=8192)
    seed: int | None = None


class TextGenerationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    backend: str
    model: str
    text: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    simulated: bool = Field(description="True when no real model produced this output.")


class RuntimeBackend(ABC):
    """Base class for inference backends."""

    name: ClassVar[str]
    display_name: ClassVar[str]
    kind: ClassVar[BackendKind]

    @abstractmethod
    async def status(self) -> BackendStatus:
        """Report availability. Must not raise for an unreachable backend."""

    @abstractmethod
    def capabilities(self) -> tuple[Capability, ...]:
        """Declare support per modality/task, including what is *not* supported."""

    @abstractmethod
    async def list_models(self) -> tuple[ModelSpec, ...]:
        """List models. Raises ``BackendUnavailableError`` if the backend cannot be reached."""

    async def generate_text(self, request: TextGenerationRequest) -> TextGenerationResult:
        raise CapabilityNotSupportedError(
            f"Backend '{self.name}' does not implement text generation in Antar yet."
        )
