"""Vocabulary shared by every Antar subsystem."""

from datetime import UTC, datetime
from enum import StrEnum


class Modality(StrEnum):
    """The five AI modalities Antar is designed around."""

    TEXT = "text"
    VISION = "vision"
    SPEECH = "speech"
    IMAGE = "image"
    VIDEO = "video"


class Task(StrEnum):
    """A concrete workload within a modality."""

    CHAT = "chat"
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    RERANKING = "reranking"
    IMAGE_UNDERSTANDING = "image_understanding"
    OCR = "ocr"
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"
    AUDIO_GENERATION = "audio_generation"
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    IMAGE_EDITING = "image_editing"
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"


def utc_now() -> datetime:
    """Timezone-aware current time; all Antar timestamps are UTC."""
    return datetime.now(UTC)
