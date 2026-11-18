"""Helpers for the OpenAI chat-completions wire format, shared by every adapter that speaks it."""

import json
import logging
from typing import Any

from antar.inference.types import ChatMessage

logger = logging.getLogger(__name__)

_SSE_DONE = "[DONE]"


def to_openai_message(message: ChatMessage) -> dict[str, Any]:
    """Render a message in the OpenAI format, images as ``image_url`` data URLs."""
    if not message.images:
        return {"role": message.role, "content": message.content}
    parts: list[dict[str, Any]] = []
    if message.content:
        parts.append({"type": "text", "text": message.content})
    parts.extend(
        {
            "type": "image_url",
            "image_url": {"url": f"data:{image.media_type};base64,{image.data_base64}"},
        }
        for image in message.images
    )
    return {"role": message.role, "content": parts}


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return None
    return float(value)


def parse_sse_data(line: str) -> dict[str, Any] | None:
    """Decode one SSE line. Returns None for anything that is not a JSON data event."""
    if not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if not data or data == _SSE_DONE:
        return None
    try:
        decoded = json.loads(data)
    except json.JSONDecodeError:
        logger.warning("Ignoring undecodable stream chunk")
        return None
    return decoded if isinstance(decoded, dict) else None


def error_message(body: object, fallback: str) -> tuple[str, str | None]:
    """Extract (message, code) from ``{"error": {"message", "code"}}`` or ``{"error": "..."}``."""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, str):
        return error, None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        code = error.get("code")
        return error["message"], code if isinstance(code, str) else None
    return fallback, None
