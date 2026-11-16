"""Mock backend for offline development and tests.

It performs no inference. Outputs are deterministic functions of the request and
are always flagged ``simulated=True`` so they can never be mistaken for, or
recorded as, real model results.
"""

import hashlib
import time
from typing import ClassVar

from antar.backends.base import (
    Availability,
    BackendKind,
    BackendStatus,
    Capability,
    RuntimeBackend,
    SupportLevel,
    TextGenerationRequest,
    TextGenerationResult,
)
from antar.core.errors import CapabilityNotSupportedError
from antar.core.types import Modality, Task
from antar.models.spec import ModelSpec

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

    async def generate_text(self, request: TextGenerationRequest) -> TextGenerationResult:
        if request.model not in {model.id for model in _MOCK_MODELS}:
            raise CapabilityNotSupportedError(f"Unknown mock model '{request.model}'.")

        started = time.perf_counter()
        digest = hashlib.sha256(
            f"{request.model}|{request.seed}|{request.prompt}".encode()
        ).digest()
        prompt_tokens = len(request.prompt.split())
        completion_tokens = min(request.max_tokens, 4 + digest[0] % 12)
        words = [_VOCABULARY[byte % len(_VOCABULARY)] for byte in digest[1 : 1 + completion_tokens]]
        return TextGenerationResult(
            backend=self.name,
            model=request.model,
            text=" ".join(words),
            prompt_tokens=prompt_tokens,
            completion_tokens=len(words),
            latency_ms=(time.perf_counter() - started) * 1000,
            simulated=True,
        )
