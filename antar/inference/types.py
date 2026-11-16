"""Inference request, result, and metric types shared by every backend."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Role = Literal["system", "user", "assistant"]
ImageMediaType = Literal["image/png", "image/jpeg", "image/webp"]

MAX_IMAGES_PER_MESSAGE = 1
MAX_IMAGES_PER_REQUEST = 4
MAX_MESSAGE_CHARS = 200_000


class ImageInput(BaseModel):
    """An image attached to a user message. Held in memory only; never persisted."""

    model_config = ConfigDict(frozen=True)

    media_type: ImageMediaType
    data_base64: str = Field(min_length=1, repr=False)


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    content: str = Field(max_length=MAX_MESSAGE_CHARS)
    # One image per message: Lemonade documents image input, but not multi-image prompts.
    images: tuple[ImageInput, ...] = Field(default=(), max_length=MAX_IMAGES_PER_MESSAGE)

    @model_validator(mode="after")
    def _images_only_from_user(self) -> "ChatMessage":
        if self.images and self.role != "user":
            raise ValueError("only user messages can carry images")
        if not self.content.strip() and not self.images:
            raise ValueError("message content must not be empty")
        return self


class GenerationSettings(BaseModel):
    """Sampling options. Every field maps to a parameter Lemonade documents for chat."""

    model_config = ConfigDict(frozen=True)

    max_tokens: int = Field(default=512, ge=1, le=16384)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    seed: int | None = Field(default=None, ge=0)
    enable_thinking: bool | None = Field(
        default=None, description="False turns reasoning off on models that think."
    )


class ChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = Field(min_length=1)
    messages: tuple[ChatMessage, ...] = Field(min_length=1, max_length=200)
    settings: GenerationSettings = GenerationSettings()

    @model_validator(mode="after")
    def _bounded_images(self) -> "ChatRequest":
        if sum(len(message.images) for message in self.messages) > MAX_IMAGES_PER_REQUEST:
            raise ValueError(f"a conversation can carry at most {MAX_IMAGES_PER_REQUEST} images")
        return self

    @property
    def has_images(self) -> bool:
        return any(message.images for message in self.messages)


class InferenceMetrics(BaseModel):
    """Measurements for one request. ``None`` always means "not available", never zero.

    Two clocks are involved and are kept apart:

    * ``latency_ms`` and ``first_chunk_ms`` are measured by Antar around the HTTP
      call to the backend. They include transport and any model load the request
      triggered.
    * ``prompt_processing_ms``, ``generation_ms`` and ``tokens_per_second`` are
      reported by the backend for this specific response.
    """

    model_config = ConfigDict(frozen=True)

    latency_ms: float = Field(ge=0, description="End to end, measured by Antar.")
    first_chunk_ms: float | None = Field(
        default=None, ge=0, description="Until the first streamed chunk arrived at Antar."
    )
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cached_prompt_tokens: int | None = Field(default=None, ge=0)
    prompt_processing_ms: float | None = Field(default=None, ge=0)
    generation_ms: float | None = Field(default=None, ge=0)
    tokens_per_second: float | None = Field(
        default=None, ge=0, description="Generation speed reported by the backend."
    )


class ChatResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    backend: str
    model: str
    content: str
    reasoning: str | None = Field(
        default=None, description="Structured reasoning output, when the backend separates it."
    )
    finish_reason: str | None = None
    metrics: InferenceMetrics
    simulated: bool = Field(description="True when no real model produced this output.")


class ChatDelta(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["delta"] = "delta"
    content: str = ""
    reasoning: str = ""


class ChatDone(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["done"] = "done"
    result: ChatResult


ChatEvent = Annotated[ChatDelta | ChatDone, Field(discriminator="type")]
