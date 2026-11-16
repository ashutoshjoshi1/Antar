"""Validation for uploaded images. Images are checked in memory and never written to disk."""

import base64
import binascii

from antar.core.errors import InvalidImageError
from antar.inference.types import ChatRequest, ImageInput

DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _sniff(data: bytes) -> str | None:
    """Identify the format from the file's own signature, not the claimed type."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image(image: ImageInput, *, max_bytes: int) -> None:
    # Reject oversized payloads before decoding them (base64 is 4/3 the size).
    if len(image.data_base64) > max_bytes * 4 // 3 + 4:
        raise InvalidImageError(f"Image is larger than the {max_bytes // (1024 * 1024)} MB limit.")
    try:
        data = base64.b64decode(image.data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidImageError("Image data is not valid base64.") from exc
    if len(data) > max_bytes:
        raise InvalidImageError(f"Image is larger than the {max_bytes // (1024 * 1024)} MB limit.")
    actual = _sniff(data)
    if actual is None:
        raise InvalidImageError("Unsupported image format. Use PNG, JPEG, or WebP.")
    if actual != image.media_type:
        raise InvalidImageError(
            f"Image is declared as {image.media_type} but its contents are {actual}."
        )


def validate_request_images(request: ChatRequest, *, max_bytes: int) -> None:
    for message in request.messages:
        for image in message.images:
            validate_image(image, max_bytes=max_bytes)
