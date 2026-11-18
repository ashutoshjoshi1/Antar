"""Mock backend for offline development and tests.

It performs no inference. Outputs are deterministic functions of the request and
are always flagged ``simulated=True`` so they can never be mistaken for, or
recorded as, real model results.
"""

import hashlib
import time
from collections.abc import AsyncIterator
from typing import ClassVar

from antar.backends.base import (
    Availability,
    BackendKind,
    BackendStatus,
    Capability,
    RuntimeBackend,
    SupportLevel,
)
from antar.core.errors import CapabilityNotSupportedError, ModelNotFoundError
from antar.core.types import Modality, Task
from antar.inference.types import (
    ChatDelta,
    ChatDone,
    ChatEvent,
    ChatRequest,
    ChatResult,
    InferenceMetrics,
)
from antar.models.spec import ExecutionLocation, ModelSpec, ModelState

_MOCK_MODELS: tuple[ModelSpec, ...] = (
    ModelSpec(
        id="mock/echo-large",
        name="Mock Echo (large)",
        backend="mock",
        modalities=(Modality.TEXT,),
        tasks=(Task.CHAT, Task.COMPLETION),
        runtime="mock",
        labels=("mock", "teacher"),
        downloaded=True,
        simulated=True,
        location=ExecutionLocation.MOCK,
        provider="mock",
        state=ModelState.LOADED,
    ),
    ModelSpec(
        id="mock/echo-small",
        name="Mock Echo (small)",
        backend="mock",
        modalities=(Modality.TEXT,),
        tasks=(Task.CHAT, Task.COMPLETION),
        runtime="mock",
        labels=("mock", "student"),
        downloaded=True,
        simulated=True,
        location=ExecutionLocation.MOCK,
        provider="mock",
        state=ModelState.LOADED,
    ),
)

_VOCABULARY = ("antar", "local", "cloud", "edge", "model", "token", "signal", "bridge")


class MockBackend(RuntimeBackend):
    name: ClassVar[str] = "mock"
    display_name: ClassVar[str] = "Mock backend"
    kind: ClassVar[BackendKind] = BackendKind.MOCK

    async def status(self) -> BackendStatus:
        return BackendStatus(
            name=self.name,
            display_name=self.display_name,
            kind=self.kind,
            availability=Availability.AVAILABLE,
            detail="In-process mock. Produces simulated output only; no model is executed.",
        )

    def capabilities(self) -> tuple[Capability, ...]:
        simulated = "Simulated output for development; not real inference."
        text = tuple(
            Capability(
                modality=Modality.TEXT, task=task, support=SupportLevel.SUPPORTED, note=simulated
            )
            for task in (Task.CHAT, Task.COMPLETION)
        )
        others = tuple(
            Capability(
                modality=modality,
                support=SupportLevel.UNSUPPORTED,
                note="The mock backend only simulates text generation.",
            )
            for modality in Modality
            if modality is not Modality.TEXT
        )
        return text + others

    async def list_models(self) -> tuple[ModelSpec, ...]:
        return _MOCK_MODELS

    async def load_model(self, model_id: str) -> None:
        """Nothing to load; accepted so pipelines can be exercised offline."""
        if model_id not in {model.id for model in _MOCK_MODELS}:
            raise ModelNotFoundError(f"Unknown mock model '{model_id}'.")

    async def unload_model(self, model_id: str) -> None:
        await self.load_model(model_id)

    async def chat(self, request: ChatRequest) -> ChatResult:
        if request.model not in {model.id for model in _MOCK_MODELS}:
            raise ModelNotFoundError(f"Unknown mock model '{request.model}'.")
        if request.has_images:
            raise CapabilityNotSupportedError("The mock backend only simulates text generation.")

        started = time.perf_counter()
        prompt = "\n".join(message.content for message in request.messages)
        seed = request.settings.seed
        digest = hashlib.sha256(f"{request.model}|{seed}|{prompt}".encode()).digest()
        count = min(request.settings.max_tokens, 4 + digest[0] % 12)
        words = [_VOCABULARY[byte % len(_VOCABULARY)] for byte in digest[1 : 1 + count]]
        # Token counts and speeds are left unset: a mock has none worth reporting.
        return ChatResult(
            backend=self.name,
            model=request.model,
            content=" ".join(words),
            finish_reason="stop",
            metrics=InferenceMetrics(latency_ms=(time.perf_counter() - started) * 1000),
            simulated=True,
        )

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        result = await self.chat(request)
        for index, word in enumerate(result.content.split(" ")):
            yield ChatDelta(content=word if index == 0 else f" {word}")
        yield ChatDone(result=result)
