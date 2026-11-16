"""The runtime backend contract.

A backend is anything that can host models: a local server, a remote GPU host,
or a mock. Every backend must be able to say whether it is reachable, what it
supports, and which models it has. Inference and model management are opt-in:
the default implementations refuse, so a backend can never appear to support something it
has not implemented.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from antar.core.errors import CapabilityNotSupportedError
from antar.core.types import Modality, Task, utc_now
from antar.inference.types import ChatEvent, ChatRequest, ChatResult
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


class DownloadJob(BaseModel):
    """Progress of a model download owned by the backend."""

    model_config = ConfigDict(frozen=True)

    model: str
    status: str
    percent: float | None = None
    bytes_downloaded: int | None = None
    bytes_total: int | None = None
    complete: bool = False


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

    async def chat(self, request: ChatRequest) -> ChatResult:
        raise CapabilityNotSupportedError(f"Backend '{self.name}' does not implement chat.")

    def chat_stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """Yield ``ChatDelta`` events, then exactly one ``ChatDone``.

        Closing the iterator must stop the backend's generation where possible.
        """
        raise CapabilityNotSupportedError(f"Backend '{self.name}' does not implement streaming.")

    async def load_model(self, model_id: str) -> None:
        raise CapabilityNotSupportedError(f"Backend '{self.name}' cannot load models.")

    async def unload_model(self, model_id: str) -> None:
        raise CapabilityNotSupportedError(f"Backend '{self.name}' cannot unload models.")

    async def download_model(self, model_id: str) -> None:
        """Start a download. Only ever called on an explicit user action."""
        raise CapabilityNotSupportedError(f"Backend '{self.name}' cannot download models.")

    async def downloads(self) -> tuple[DownloadJob, ...]:
        return ()

    async def model_processes(self) -> tuple[tuple[str, int | None], ...]:
        """(model id, process id) for each model in memory, where the backend reports it."""
        return ()
