"""Lemonade backend adapter: connectivity and model discovery.

Inference through Lemonade is not wired up yet. Capabilities are therefore
reported as ``DOCUMENTED`` (Lemonade documents the endpoint) rather than
``SUPPORTED`` (Antar can run it).
"""

from typing import ClassVar

from antar.backends.base import (
    Availability,
    BackendKind,
    BackendStatus,
    Capability,
    RuntimeBackend,
    SupportLevel,
)
from antar.backends.lemonade.client import LemonadeClient, LemonadeModel
from antar.core.errors import BackendUnavailableError
from antar.core.types import Modality, Task
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


def to_model_spec(model: LemonadeModel) -> ModelSpec:
    """Convert a Lemonade model entry into an Antar ModelSpec."""
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
        except BackendUnavailableError as exc:
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
        documented = tuple(
            Capability(
                modality=modality,
                task=task,
                support=SupportLevel.DOCUMENTED,
                note=_ADAPTER_NOTE.format(endpoint=endpoint),
            )
            for modality, task, endpoint in _DOCUMENTED
        )
        video = Capability(
            modality=Modality.VIDEO,
            support=SupportLevel.UNSUPPORTED,
            note="Lemonade documents no video generation endpoint.",
        )
        return (*documented, video)

    async def list_models(self) -> tuple[ModelSpec, ...]:
        models = await self._client.list_models(show_all=True)
        return tuple(to_model_spec(model) for model in models)
