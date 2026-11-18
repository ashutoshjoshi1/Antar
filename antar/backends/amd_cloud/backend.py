"""AMD cloud backend: a self-hosted vLLM server on AMD Instinct GPUs.

Antar talks to exactly one HTTP destination, the endpoint in its own settings
(normally the near end of an SSH tunnel), and runs only fixed read-only
commands over SSH. It does not start vLLM, the virtual machine, or anything
else that costs money: the operator does that with ``scripts/cloud/``.

Text chat and image understanding are ``SUPPORTED`` as adapters with mocked
tests. Whether a given model, image, and driver combination works is only
known once it has been run on a real host; see ``docs/phase2-amd-cloud.md``.
"""

from collections.abc import AsyncGenerator
from typing import ClassVar

from antar.backends.amd_cloud.amd_smi import GpuMonitor
from antar.backends.amd_cloud.config import (
    AmdCloudProfile,
    CloudEndpointSettings,
    CloudModelConfig,
)
from antar.backends.amd_cloud.vllm import VllmClient, VllmCompletion, VllmModel
from antar.backends.base import (
    Availability,
    BackendKind,
    BackendStatus,
    Capability,
    RuntimeBackend,
    SupportLevel,
)
from antar.core.errors import (
    BackendRequestError,
    BackendUnavailableError,
    CapabilityNotSupportedError,
    ModelNotFoundError,
)
from antar.core.types import Modality, Task
from antar.hardware.gpu import GpuSample
from antar.inference.types import ChatDone, ChatEvent, ChatRequest, ChatResult
from antar.models.catalog import find_known_model
from antar.models.spec import ExecutionLocation, ModelSpec, ModelState

_SPECIALIZED = (
    "Planned. Needs a specialized cloud worker; vLLM is not assumed to run this modality. "
    "See docs/architecture/cloud-execution.md."
)
_TASKS = {Modality.TEXT: Task.CHAT, Modality.VISION: Task.IMAGE_UNDERSTANDING}


class AmdCloudBackend(RuntimeBackend):
    name: ClassVar[str] = "amd_cloud"
    display_name: ClassVar[str] = "AMD cloud (vLLM on ROCm)"
    kind: ClassVar[BackendKind] = BackendKind.CLOUD

    def __init__(
        self,
        profile: AmdCloudProfile | None = None,
        *,
        endpoint: CloudEndpointSettings | None = None,
        client: VllmClient | None = None,
        monitor: GpuMonitor | None = None,
    ) -> None:
        self._profile = profile
        self._endpoint = endpoint
        self._client = client
        self._monitor = monitor

    def _status(
        self, availability: Availability, detail: str, version: str | None = None
    ) -> BackendStatus:
        return BackendStatus(
            name=self.name,
            display_name=self.display_name,
            kind=self.kind,
            availability=availability,
            detail=detail,
            endpoint=self._client.base_url if self._client else None,
            version=version,
        )

    def _require_client(self) -> VllmClient:
        if self._client is None:
            raise BackendUnavailableError(
                "No cloud endpoint is configured. Set ANTAR_CLOUD__BASE_URL; see "
                "docs/cloud/secure-access.md."
            )
        return self._client

    async def status(self) -> BackendStatus:
        if self._client is None:
            return self._status(
                Availability.NOT_CONFIGURED,
                "No cloud endpoint configured. Set ANTAR_CLOUD__BASE_URL to the tunnelled "
                "vLLM address; see docs/cloud/secure-access.md.",
            )
        try:
            await self._client.health()
            models = await self._client.list_models()
        except (BackendUnavailableError, BackendRequestError) as exc:
            return self._status(Availability.UNAVAILABLE, str(exc))
        served = ", ".join(model.id for model in models)
        detail = f"Connected. Serving: {served}." if served else "Connected. No model is served."
        return self._status(Availability.AVAILABLE, detail, await self._client.version())

    def capabilities(self) -> tuple[Capability, ...]:
        served_note = "Runs through vLLM POST /v1/chat/completions."
        return (
            Capability(
                modality=Modality.TEXT,
                task=Task.CHAT,
                support=SupportLevel.SUPPORTED,
                note=served_note,
            ),
            Capability(
                modality=Modality.VISION,
                task=Task.IMAGE_UNDERSTANDING,
                support=SupportLevel.SUPPORTED,
                note=served_note + " The served model must be a vision-language model.",
            ),
            *(
                Capability(modality=modality, support=SupportLevel.PLANNED, note=_SPECIALIZED)
                for modality in (Modality.SPEECH, Modality.IMAGE, Modality.VIDEO)
            ),
        )

    def _declared(self, model_id: str) -> CloudModelConfig | None:
        models = self._endpoint.models if self._endpoint else ()
        return next((model for model in models if model.id == model_id), None)

    def _spec(self, model_id: str, served: VllmModel | None) -> ModelSpec:
        declared = self._declared(model_id)
        known = find_known_model(
            declared.source if declared else None, served.root if served else None, model_id
        )
        if declared is not None:
            modalities = declared.modalities
        else:
            # Unknown models stay unclassified: vLLM's model list does not say what they accept.
            modalities = known.modalities if known else ()
        return ModelSpec(
            id=model_id,
            name=known.name if known else model_id,
            backend=self.name,
            modalities=modalities,
            tasks=tuple(_TASKS[modality] for modality in modalities if modality in _TASKS),
            revision=declared.revision if declared else None,
            checkpoint=(declared.source if declared else None)
            or (known.id if known else None)
            or (served.root if served else None),
            runtime="vllm",
            size_bytes=known.weights_bytes if known else None,
            license=(declared.license if declared else None) or (known.license if known else None),
            downloaded=True if served else None,
            loaded=served is not None,
            quantization=known.precision if known else None,
            # What the server was started with, not the model's theoretical maximum.
            context_length=served.max_model_len if served else None,
            location=ExecutionLocation.CLOUD,
            provider="vllm",
            state=ModelState.LOADED if served else ModelState.CONFIGURED,
            family=known.family if known else None,
            parameter_count=known.parameter_count if known else None,
        )

    async def list_models(self) -> tuple[ModelSpec, ...]:
        if self._client is None:
            return ()
        served = await self._client.list_models()
        served_ids = {model.id for model in served}
        declared = self._endpoint.models if self._endpoint else ()
        return (
            *(self._spec(model.id, model) for model in served),
            *(self._spec(model.id, None) for model in declared if model.id not in served_ids),
        )

    async def _require_served(self, model_id: str, *, vision: bool = False) -> ModelSpec:
        models = await self.list_models() if self._client else ()
        self._require_client()
        spec = next((model for model in models if model.id == model_id and model.loaded), None)
        if spec is None:
            served = ", ".join(model.id for model in models if model.loaded) or "nothing"
            raise ModelNotFoundError(
                f"The cloud endpoint is not serving '{model_id}' (serving: {served}). vLLM "
                "serves the model it was started with; see scripts/cloud/start_vllm.sh."
            )
        if vision and Modality.VISION not in spec.modalities:
            raise CapabilityNotSupportedError(
                f"'{model_id}' is not known to accept images. If it is a vision-language "
                "model, declare it under cloud.models with modalities [text, vision]."
            )
        return spec

    async def load_model(self, model_id: str) -> None:
        """vLLM serves one model, chosen when it starts. This only confirms it is the one."""
        await self._require_served(model_id)

    def _result(self, request: ChatRequest, completion: VllmCompletion) -> ChatResult:
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
        await self._require_served(request.model, vision=request.has_images)
        return self._result(request, await self._require_client().chat(request))

    async def chat_stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
        await self._require_served(request.model, vision=request.has_images)
        async for event in self._require_client().chat_stream(request):
            if isinstance(event, VllmCompletion):
                yield ChatDone(result=self._result(request, event))
            else:
                yield event

    async def ping_ms(self) -> float:
        """Round-trip time of one ``/health`` call: the cost of the path to the server."""
        return await self._require_client().health()

    async def gpu_sample(self) -> GpuSample | None:
        return await self._monitor.sample() if self._monitor else None
