"""Optimization job specification and technique applicability.

Nothing in this module executes an optimization. It defines what a job *is* and
which techniques are worth considering for a modality, so that invalid
combinations are rejected before any compute is spent.
"""

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from antar.core.types import Modality, Task, utc_now
from antar.models.spec import ModelRef


class OptimizationTechnique(StrEnum):
    LORA = "lora"
    QLORA = "qlora"
    DISTILLATION = "distillation"
    QUANTIZATION = "quantization"
    RUNTIME_TUNING = "runtime_tuning"
    HYBRID_ROUTING = "hybrid_routing"


class Applicability(StrEnum):
    CANDIDATE = "candidate"
    LIMITED = "limited"
    NOT_APPLICABLE = "not_applicable"


class TechniqueApplicability(BaseModel):
    model_config = ConfigDict(frozen=True)

    technique: OptimizationTechnique
    modality: Modality
    applicability: Applicability
    note: str
    implemented: bool = Field(
        default=False, description="Whether Antar can execute this combination today."
    )


_T = OptimizationTechnique
_M = Modality
_A = Applicability

# Applicability reflects common practice in the literature, not measured Antar
# results. Every entry is `implemented=False` until a real executor lands.
_MATRIX: dict[tuple[OptimizationTechnique, Modality], tuple[Applicability, str]] = {
    (_T.LORA, _M.TEXT): (_A.CANDIDATE, "Adapter fine-tuning of transformer LLMs via PEFT."),
    (_T.LORA, _M.VISION): (_A.CANDIDATE, "Adapters on the language tower and/or projector."),
    (_T.LORA, _M.SPEECH): (_A.LIMITED, "Used for ASR encoders; TTS support is model-specific."),
    (_T.LORA, _M.IMAGE): (_A.CANDIDATE, "Widely used for diffusion model adaptation."),
    (_T.LORA, _M.VIDEO): (_A.LIMITED, "Model-specific; memory cost is high."),
    (_T.QLORA, _M.TEXT): (_A.CANDIDATE, "4-bit base model with LoRA adapters."),
    (_T.QLORA, _M.VISION): (_A.LIMITED, "Depends on quantized loading of the vision tower."),
    (_T.QLORA, _M.SPEECH): (_A.NOT_APPLICABLE, "No established QLoRA path for speech models."),
    (_T.QLORA, _M.IMAGE): (_A.NOT_APPLICABLE, "No established QLoRA path for diffusion models."),
    (_T.QLORA, _M.VIDEO): (_A.NOT_APPLICABLE, "No established QLoRA path for video models."),
    (_T.DISTILLATION, _M.TEXT): (_A.CANDIDATE, "Teacher-student training on task data."),
    (_T.DISTILLATION, _M.VISION): (_A.LIMITED, "Requires a compatible smaller VLM student."),
    (_T.DISTILLATION, _M.SPEECH): (_A.CANDIDATE, "Established for ASR (smaller decoders)."),
    (_T.DISTILLATION, _M.IMAGE): (_A.CANDIDATE, "Step distillation reduces sampling steps."),
    (_T.DISTILLATION, _M.VIDEO): (_A.LIMITED, "Step distillation exists; very compute-heavy."),
    (_T.QUANTIZATION, _M.TEXT): (_A.CANDIDATE, "Weight quantization, e.g. GGUF formats."),
    (_T.QUANTIZATION, _M.VISION): (_A.CANDIDATE, "Language tower quantizes well; check OCR."),
    (_T.QUANTIZATION, _M.SPEECH): (_A.CANDIDATE, "Common for whisper.cpp-style runtimes."),
    (_T.QUANTIZATION, _M.IMAGE): (_A.LIMITED, "Quality is sensitive below 8-bit."),
    (_T.QUANTIZATION, _M.VIDEO): (_A.LIMITED, "Quality is sensitive; verify temporal stability."),
    **{
        (_T.RUNTIME_TUNING, modality): (
            _A.CANDIDATE,
            "Backend settings such as context size, batch size, and device placement.",
        )
        for modality in Modality
    },
    **{
        (_T.HYBRID_ROUTING, modality): (
            _A.CANDIDATE,
            "Route between local and cloud by capability and measured constraints.",
        )
        for modality in Modality
    },
}

TECHNIQUE_MATRIX: tuple[TechniqueApplicability, ...] = tuple(
    TechniqueApplicability(
        technique=technique, modality=modality, applicability=applicability, note=note
    )
    for (technique, modality), (applicability, note) in _MATRIX.items()
)


def applicability_of(technique: OptimizationTechnique, modality: Modality) -> Applicability:
    return _MATRIX[(technique, modality)][0]


class TechniqueConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    technique: OptimizationTechnique
    params: dict[str, JsonValue] = Field(
        default_factory=dict, description="Technique-specific settings, e.g. LoRA rank."
    )


class OptimizationConstraints(BaseModel):
    """What the deployed model must satisfy. Unset means unconstrained."""

    model_config = ConfigDict(frozen=True)

    max_memory_gb: float | None = Field(default=None, gt=0)
    max_latency_ms: float | None = Field(default=None, gt=0)
    min_throughput: float | None = Field(
        default=None, gt=0, description="In the modality's throughput unit, e.g. tokens/s."
    )
    max_quality_drop: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Largest acceptable relative drop in the primary quality metric.",
    )


class JobStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OptimizationJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    model: ModelRef
    modality: Modality
    task: Task
    techniques: tuple[TechniqueConfig, ...] = Field(min_length=1)
    constraints: OptimizationConstraints = OptimizationConstraints()
    execution_backend: str = Field(description="Backend that runs the optimization itself.")
    target_backend: str = Field(description="Backend the optimized model is meant to deploy on.")
    seed: int | None = None
    status: JobStatus = JobStatus.DRAFT
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _techniques_apply_to_modality(self) -> Self:
        rejected = [
            config.technique.value
            for config in self.techniques
            if applicability_of(config.technique, self.modality) is Applicability.NOT_APPLICABLE
        ]
        if rejected:
            raise ValueError(
                f"Not applicable to the {self.modality.value} modality: {', '.join(rejected)}"
            )
        return self
