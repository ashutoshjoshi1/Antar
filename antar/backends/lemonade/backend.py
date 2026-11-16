"""Lemonade backend adapter: discovery, model management, and chat inference.

Text chat and image understanding are ``SUPPORTED``: Antar runs them through
``POST /v1/chat/completions``. Everything else Lemonade documents stays
``DOCUMENTED`` until Antar has an adapter and a test for it.

Lemonade's ``/load`` and ``/chat/completions`` download a missing model on
their own. Antar never lets that happen implicitly: every call that could
trigger it first checks that the weights are already present.
"""

import re
from collections.abc import AsyncGenerator
from typing import ClassVar

from antar.backends.base import (
    Availability,
    BackendKind,
    BackendStatus,
    Capability,
    DownloadJob,
    RuntimeBackend,
    SupportLevel,
)
from antar.backends.lemonade.client import (
    LemonadeClient,
    LemonadeCompletion,
    LemonadeModel,
    LemonadeStats,
)
from antar.core.errors import (
    BackendRequestError,
    BackendUnavailableError,
    CapabilityNotSupportedError,
    ModelNotDownloadedError,
    ModelNotFoundError,
)
from antar.core.types import Modality, Task
from antar.inference.types import ChatDone, ChatEvent, ChatRequest, ChatResult
from antar.models.spec import ModelSpec

# Lemonade model labels -> Antar (modality, task). Labels come from the model
# list reference (docs/api/openai.md). Labels not listed here are kept verbatim
# on the ModelSpec but do not affect classification.
_LABEL_MAP: dict[str, tuple[Modality, Task]] = {
    "chat": (Modality.TEXT, Task.CHAT),
    "embeddings": (Modality.TEXT, Task.EMBEDDING),
    "embedding": (Modality.TEXT, Task.EMBEDDING),
    "reranking": (Modality.TEXT, Task.RERANKING),
    "vision": (Modality.VISION, Task.IMAGE_UNDERSTANDING),
    "transcription": (Modality.SPEECH, Task.SPEECH_TO_TEXT),
    "tts": (Modality.SPEECH, Task.TEXT_TO_SPEECH),
    "audio-generation": (Modality.SPEECH, Task.AUDIO_GENERATION),
    "image": (Modality.IMAGE, Task.TEXT_TO_IMAGE),
    "edit": (Modality.IMAGE, Task.IMAGE_EDITING),
}
_DEPLOYMENT_LABELS = frozenset(_LABEL_MAP) - {"vision", "edit"}

# A model with no deployment label inherits its recipe's default. Only the
# llamacpp default is stated in the docs, so only that one is applied.
_RECIPE_DEFAULT_LABEL = {"llamacpp": "chat"}

_BYTES_PER_GB = 1_000_000_000

# Quantization variant as named in a checkpoint, e.g. "repo:Q4_K_M" or "x-Q4_0.gguf".
_QUANTIZATION = re.compile(
    r"(?<![A-Za-z0-9])((?:Q\d|IQ\d|F16|F32|BF16)[A-Za-z0-9_]*)", re.IGNORECASE
)

_SUPPORTED: frozenset[tuple[Modality, Task]] = frozenset(
    {(Modality.TEXT, Task.CHAT), (Modality.VISION, Task.IMAGE_UNDERSTANDING)}
)

_ADAPTER_NOTE = "Documented by Lemonade ({endpoint}); Antar inference adapter not implemented yet."

_DOCUMENTED: tuple[tuple[Modality, Task, str], ...] = (
    (Modality.TEXT, Task.CHAT, "POST /v1/chat/completions"),
    (Modality.TEXT, Task.COMPLETION, "POST /v1/completions"),
    (Modality.TEXT, Task.EMBEDDING, "POST /v1/embeddings"),
    (Modality.TEXT, Task.RERANKING, "POST /v1/rerank"),
    (Modality.VISION, Task.IMAGE_UNDERSTANDING, "image_url content in chat completions"),
    (Modality.SPEECH, Task.SPEECH_TO_TEXT, "POST /v1/audio/transcriptions"),
    (Modality.SPEECH, Task.TEXT_TO_SPEECH, "POST /v1/audio/speech"),
    (Modality.SPEECH, Task.AUDIO_GENERATION, "POST /v1/audio/generations"),
    (Modality.IMAGE, Task.TEXT_TO_IMAGE, "POST /v1/images/generations"),
    (Modality.IMAGE, Task.IMAGE_EDITING, "POST /v1/images/edits"),
    (Modality.IMAGE, Task.IMAGE_TO_IMAGE, "POST /v1/images/variations"),
)


def parse_quantization(checkpoint: str | None) -> str | None:
    """The quantization variant a checkpoint names, or None if it names none."""
    if not checkpoint or ":" not in checkpoint:
        return None
    variant = checkpoint.split(":", 1)[1].removesuffix(".gguf")
    matches = _QUANTIZATION.findall(variant)
    return matches[-1].upper() if matches else None


def to_model_spec(model: LemonadeModel, loaded: frozenset[str] | None = None) -> ModelSpec:
    """Convert a Lemonade model entry into an Antar ModelSpec.

    ``loaded`` is the set of model names currently in memory, or None if unknown.
    """
    labels = model.labels
    effective = set(labels)
    if not effective & _DEPLOYMENT_LABELS and model.recipe in _RECIPE_DEFAULT_LABEL:
        effective.add(_RECIPE_DEFAULT_LABEL[model.recipe])

    pairs = [_LABEL_MAP[label] for label in sorted(effective) if label in _LABEL_MAP]
    modalities = tuple(dict.fromkeys(modality for modality, _ in pairs))
    tasks = tuple(dict.fromkeys(task for _, task in pairs))
    return ModelSpec(
        id=model.id,
        name=model.id,
        backend=LemonadeBackend.name,
        modalities=modalities,
        tasks=tasks,
        checkpoint=model.checkpoint,
        runtime=model.recipe,
        size_bytes=round(model.size * _BYTES_PER_GB) if model.size is not None else None,
        downloaded=model.downloaded,
        loaded=model.id in loaded if loaded is not None else None,
        quantization=parse_quantization(model.checkpoint),
        context_length=model.max_context_window,
        labels=labels,
    )


class LemonadeBackend(RuntimeBackend):
    name: ClassVar[str] = "lemonade"
    display_name: ClassVar[str] = "Lemonade (local)"
    kind: ClassVar[BackendKind] = BackendKind.LOCAL

    def __init__(self, client: LemonadeClient) -> None:
        self._client = client

    async def status(self) -> BackendStatus:
        try:
            health = await self._client.health()
        except (BackendUnavailableError, BackendRequestError) as exc:
            return self._status(Availability.UNAVAILABLE, str(exc))

        if health.status != "ok":
            return self._status(
                Availability.UNAVAILABLE,
                f"Lemonade reported status '{health.status}'.",
                version=health.version,
            )
        loaded = ", ".join(model.model_name for model in health.all_models_loaded)
        detail = f"Connected. Loaded models: {loaded}." if loaded else "Connected. No model loaded."
        return self._status(Availability.AVAILABLE, detail, version=health.version)

    def _status(
        self, availability: Availability, detail: str, version: str | None = None
    ) -> BackendStatus:
        return BackendStatus(
            name=self.name,
            display_name=self.display_name,
            kind=self.kind,
            availability=availability,
            detail=detail,
            endpoint=self._client.base_url,
            version=version,
        )

    def capabilities(self) -> tuple[Capability, ...]:
        declared = tuple(
            Capability(
                modality=modality,
                task=task,
                support=SupportLevel.SUPPORTED
                if (modality, task) in _SUPPORTED
                else SupportLevel.DOCUMENTED,
                note=f"Runs through {endpoint}."
                if (modality, task) in _SUPPORTED
                else _ADAPTER_NOTE.format(endpoint=endpoint),
            )
            for modality, task, endpoint in _DOCUMENTED
        )
        video = Capability(
            modality=Modality.VIDEO,
            support=SupportLevel.UNSUPPORTED,
            note="Lemonade documents no video generation endpoint.",
        )
        return (*declared, video)

    async def list_models(self) -> tuple[ModelSpec, ...]:
        models = await self._client.list_models(show_all=True)
        health = await self._client.health()
        loaded = frozenset(model.model_name for model in health.all_models_loaded)
        return tuple(to_model_spec(model, loaded) for model in models)

    async def stats(self) -> LemonadeStats:
        return await self._client.stats()

    async def model_processes(self) -> tuple[tuple[str, int | None], ...]:
        health = await self._client.health()
        return tuple((model.model_name, model.pid) for model in health.all_models_loaded)

    async def _require_downloaded(self, model_id: str, *, vision: bool = False) -> ModelSpec:
        """Refuse anything that would make Lemonade download weights implicitly."""
        models = await self.list_models()
        spec = next((model for model in models if model.id == model_id), None)
        if spec is None:
            raise ModelNotFoundError(f"Lemonade has no model named '{model_id}'.")
        if spec.downloaded is not True:
            raise ModelNotDownloadedError(
                f"'{model_id}' is not downloaded. Download it from the Models page first."
            )
        if vision and Modality.VISION not in spec.modalities:
            raise CapabilityNotSupportedError(
                f"'{model_id}' does not accept images. Choose a model labelled 'vision'."
            )
        return spec

    async def load_model(self, model_id: str) -> None:
        await self._require_downloaded(model_id)
        await self._client.load(model_id)

    async def unload_model(self, model_id: str) -> None:
        await self._client.unload(model_id)

    async def download_model(self, model_id: str) -> None:
        models = await self._client.list_models(show_all=True)
        if not any(model.id == model_id for model in models):
            raise ModelNotFoundError(f"Lemonade has no model named '{model_id}'.")
        await self._client.pull(model_id)

    async def downloads(self) -> tuple[DownloadJob, ...]:
        return tuple(
            DownloadJob(
                model=job.model_name,
                status=job.status,
                percent=job.percent,
                bytes_downloaded=job.overall_bytes_downloaded,
                bytes_total=job.total_download_size or None,
                complete=job.complete,
            )
            for job in await self._client.downloads()
        )

    def _result(self, request: ChatRequest, completion: LemonadeCompletion) -> ChatResult:
        return ChatResult(
            backend=self.name,
            model=request.model,
            content=completion.content,
            reasoning=completion.reasoning,
            finish_reason=completion.finish_reason,
            metrics=completion.metrics,
            simulated=False,
        )

    async def chat(self, request: ChatRequest) -> ChatResult:
        await self._require_downloaded(request.model, vision=request.has_images)
        return self._result(request, await self._client.chat(request))

    async def chat_stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
        await self._require_downloaded(request.model, vision=request.has_images)
        async for event in self._client.chat_stream(request):
            if isinstance(event, LemonadeCompletion):
                yield ChatDone(result=self._result(request, event))
            else:
                yield event
