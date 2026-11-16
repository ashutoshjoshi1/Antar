"""Generate text with the mock backend. Runs offline; output is simulated.

uv run python examples/text/mock_generation.py
"""

import asyncio

from antar.backends.mock.backend import MockBackend
from antar.inference.types import ChatMessage, ChatRequest, GenerationSettings


async def main() -> None:
    backend = MockBackend()
    for model in await backend.list_models():
        request = ChatRequest(
            model=model.id,
            messages=(ChatMessage(role="user", content="Explain quantization."),),
            settings=GenerationSettings(seed=7),
        )
        result = await backend.chat(request)
        print(f"{result.model}: {result.content!r} (simulated={result.simulated})")


if __name__ == "__main__":
    asyncio.run(main())
