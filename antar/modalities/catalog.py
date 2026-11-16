"""The modality catalog: tasks and evaluation metrics appropriate to each modality.

This is descriptive metadata, not an implementation. It records which metrics
Antar intends to use per modality so that experiments are compared on measures
that make sense for the workload. Listing a metric here does not mean an
evaluator for it exists yet — see ``docs/benchmarks/methodology.md``.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from antar.core.types import Modality, Task


class MetricKind(StrEnum):
    QUALITY = "quality"
    PERFORMANCE = "performance"


class MetricSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    name: str
    kind: MetricKind
    higher_is_better: bool
    unit: str | None = None
    applies_to: tuple[Task, ...] = ()


class ModalityInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    modality: Modality
    description: str
    tasks: tuple[Task, ...]
    metrics: tuple[MetricSpec, ...]


def _quality(
    key: str, name: str, *, higher: bool, unit: str | None = None, tasks: tuple[Task, ...] = ()
) -> MetricSpec:
    return MetricSpec(
        key=key,
        name=name,
        kind=MetricKind.QUALITY,
        higher_is_better=higher,
        unit=unit,
        applies_to=tasks,
    )


def _perf(key: str, name: str, *, higher: bool, unit: str) -> MetricSpec:
    return MetricSpec(
        key=key, name=name, kind=MetricKind.PERFORMANCE, higher_is_better=higher, unit=unit
    )


_PEAK_MEMORY = _perf("peak_memory_bytes", "Peak memory", higher=False, unit="bytes")
_LATENCY = _perf("latency_ms", "End-to-end latency", higher=False, unit="ms")

MODALITY_CATALOG: tuple[ModalityInfo, ...] = (
    ModalityInfo(
        modality=Modality.TEXT,
        description="LLMs, reasoning and coding models, embeddings, tool-calling agents.",
        tasks=(Task.CHAT, Task.COMPLETION, Task.EMBEDDING, Task.RERANKING),
        metrics=(
            _quality("task_accuracy", "Task accuracy", higher=True, unit="ratio"),
            _quality("perplexity", "Perplexity", higher=False, tasks=(Task.COMPLETION,)),
            _quality(
                "tool_call_validity",
                "Valid tool-call rate",
                higher=True,
                unit="ratio",
                tasks=(Task.CHAT,),
            ),
            _perf("time_to_first_token_ms", "Time to first token", higher=False, unit="ms"),
            _perf("tokens_per_second", "Generation throughput", higher=True, unit="tokens/s"),
            _PEAK_MEMORY,
        ),
    ),
    ModalityInfo(
        modality=Modality.VISION,
        description="Vision-language models, OCR, image understanding.",
        tasks=(Task.IMAGE_UNDERSTANDING, Task.OCR),
        metrics=(
            _quality(
                "vqa_accuracy",
                "VQA accuracy",
                higher=True,
                unit="ratio",
                tasks=(Task.IMAGE_UNDERSTANDING,),
            ),
            _quality(
                "character_error_rate",
                "Character error rate",
                higher=False,
                unit="ratio",
                tasks=(Task.OCR,),
            ),
            _perf("time_to_first_token_ms", "Time to first token", higher=False, unit="ms"),
            _perf("tokens_per_second", "Generation throughput", higher=True, unit="tokens/s"),
            _PEAK_MEMORY,
        ),
    ),
    ModalityInfo(
        modality=Modality.SPEECH,
        description="Speech-to-text, text-to-speech, audio generation.",
        tasks=(Task.SPEECH_TO_TEXT, Task.TEXT_TO_SPEECH, Task.AUDIO_GENERATION),
        metrics=(
            _quality(
                "word_error_rate",
                "Word error rate",
                higher=False,
                unit="ratio",
                tasks=(Task.SPEECH_TO_TEXT,),
            ),
            _quality(
                "tts_intelligibility_wer",
                "Round-trip intelligibility (ASR WER on synthesized speech)",
                higher=False,
                unit="ratio",
                tasks=(Task.TEXT_TO_SPEECH,),
            ),
            _perf("real_time_factor", "Real-time factor", higher=False, unit="x"),
            _LATENCY,
            _PEAK_MEMORY,
        ),
    ),
    ModalityInfo(
        modality=Modality.IMAGE,
        description="Text-to-image, image-to-image, image editing.",
        tasks=(Task.TEXT_TO_IMAGE, Task.IMAGE_TO_IMAGE, Task.IMAGE_EDITING),
        metrics=(
            _quality("clip_score", "CLIP text-image alignment", higher=True),
            _quality("fid", "Fréchet Inception Distance", higher=False),
            _quality(
                "lpips",
                "LPIPS perceptual distance to reference",
                higher=False,
                tasks=(Task.IMAGE_TO_IMAGE, Task.IMAGE_EDITING),
            ),
            _perf("seconds_per_image", "Time per image", higher=False, unit="s"),
            _PEAK_MEMORY,
        ),
    ),
    ModalityInfo(
        modality=Modality.VIDEO,
        description="Text-to-video and image-to-video generation pipelines.",
        tasks=(Task.TEXT_TO_VIDEO, Task.IMAGE_TO_VIDEO),
        metrics=(
            _quality("fvd", "Fréchet Video Distance", higher=False),
            _quality("clip_score", "CLIP text-frame alignment", higher=True),
            _quality("temporal_consistency", "Frame-to-frame CLIP consistency", higher=True),
            _perf("seconds_per_frame", "Time per generated frame", higher=False, unit="s"),
            _PEAK_MEMORY,
        ),
    ),
)


def get_modality_info(modality: Modality) -> ModalityInfo:
    return next(info for info in MODALITY_CATALOG if info.modality == modality)


def metric_keys_for(modality: Modality) -> frozenset[str]:
    return frozenset(metric.key for metric in get_modality_info(modality).metrics)
