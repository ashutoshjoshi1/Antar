"""Generate text with the mock backend. Runs offline; output is simulated.

uv run python examples/text/mock_generation.py
"""

import asyncio

from antar.backends.base import TextGenerationRequest
from antar.backends.mock.backend import MockBackend


async def main() -> None:
    backend = MockBackend()
    for model in await backend.list_models():
        result = await backend.generate_text(
            TextGenerationRequest(model=model.id, prompt="Explain quantization.", seed=7)
        )
        print(f"{result.model}: {result.text!r} (simulated={result.simulated})")


if __name__ == "__main__":
    asyncio.run(main())
