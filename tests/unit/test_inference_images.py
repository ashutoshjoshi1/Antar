import base64

import pytest
from pydantic import ValidationError

from antar.core.errors import CapabilityNotSupportedError, InvalidImageError
from antar.inference.images import validate_image
from antar.inference.service import InferenceService
from antar.inference.types import ChatMessage, ChatRequest, GenerationSettings, ImageInput

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24
LIMIT = 1024


def _image(data: bytes, media_type: str = "image/png") -> ImageInput:
    return ImageInput.model_validate(
        {"media_type": media_type, "data_base64": base64.b64encode(data).decode()}
    )


@pytest.mark.parametrize(
    ("data", "media_type"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp")],
)
def test_supported_formats_are_accepted(data: bytes, media_type: str) -> None:
    validate_image(_image(data, media_type), max_bytes=LIMIT)


def test_declared_type_must_match_the_file_contents() -> None:
    with pytest.raises(InvalidImageError, match="declared as image/png but its contents are"):
        validate_image(_image(JPEG, "image/png"), max_bytes=LIMIT)


def test_unrecognized_contents_are_rejected() -> None:
    with pytest.raises(InvalidImageError, match="Unsupported image format"):
        validate_image(_image(b"GIF89a" + b"\x00" * 32), max_bytes=LIMIT)


def test_oversized_image_is_rejected() -> None:
    with pytest.raises(InvalidImageError, match="larger than"):
        validate_image(_image(PNG + b"\x00" * LIMIT), max_bytes=LIMIT)


def test_invalid_base64_is_rejected() -> None:
    image = ImageInput(media_type="image/png", data_base64="not base64!!")

    with pytest.raises(InvalidImageError, match="not valid base64"):
        validate_image(image, max_bytes=LIMIT)


def test_unsupported_media_type_is_rejected_by_the_schema() -> None:
    with pytest.raises(ValidationError):
        _image(PNG, "image/gif")


def test_only_one_image_per_message() -> None:
    with pytest.raises(ValidationError):
        ChatMessage(role="user", content="compare", images=(_image(PNG), _image(PNG)))


def test_only_user_messages_can_carry_images() -> None:
    with pytest.raises(ValidationError, match="only user messages"):
        ChatMessage(role="assistant", content="here", images=(_image(PNG),))


def test_empty_message_is_rejected_unless_it_has_an_image() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        ChatMessage(role="user", content="   ")

    assert ChatMessage(role="user", content="", images=(_image(PNG),)).images


@pytest.mark.parametrize("settings", [{"max_tokens": 0}, {"temperature": 3}, {"top_p": 0}])
def test_generation_settings_reject_out_of_range_values(settings: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        GenerationSettings.model_validate(settings)


def test_service_validates_images_before_choosing_a_backend() -> None:
    service = InferenceService([], max_image_bytes=LIMIT)
    request = ChatRequest(
        model="m", messages=(ChatMessage(role="user", content="x", images=(_image(b"bad"),)),)
    )

    with pytest.raises(InvalidImageError):
        service.chat_stream("lemonade", request)


def test_service_rejects_a_backend_that_is_not_configured() -> None:
    service = InferenceService([], max_image_bytes=LIMIT)
    request = ChatRequest(model="m", messages=(ChatMessage(role="user", content="x"),))

    with pytest.raises(CapabilityNotSupportedError, match="Unknown backend"):
        service.chat_stream("http://evil.example", request)
