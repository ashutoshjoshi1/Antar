"""Backend selection and request validation for inference.

Backends are chosen by *name* from the configured registry. There is no way to
pass a URL: the only HTTP targets Antar will call are the ones in its settings.
"""

from collections.abc import AsyncIterator, Sequence

from antar.backends.base import RuntimeBackend
from antar.core.errors import CapabilityNotSupportedError
from antar.inference.images import validate_request_images
from antar.inference.types import ChatEvent, ChatRequest, ChatResult


def get_backend(backends: Sequence[RuntimeBackend], name: str) -> RuntimeBackend:
    backend = next((candidate for candidate in backends if candidate.name == name), None)
    if backend is None:
        known = ", ".join(candidate.name for candidate in backends)
        raise CapabilityNotSupportedError(f"Unknown backend '{name}'. Configured: {known}.")
    return backend


class InferenceService:
    def __init__(self, backends: Sequence[RuntimeBackend], *, max_image_bytes: int) -> None:
        self._backends = tuple(backends)
        self._max_image_bytes = max_image_bytes

    def _prepare(self, backend: str, request: ChatRequest) -> RuntimeBackend:
        validate_request_images(request, max_bytes=self._max_image_bytes)
        return get_backend(self._backends, backend)

    async def chat(self, backend: str, request: ChatRequest) -> ChatResult:
        return await self._prepare(backend, request).chat(request)

    def chat_stream(self, backend: str, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        return self._prepare(backend, request).chat_stream(request)
