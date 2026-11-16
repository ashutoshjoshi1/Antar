"""Built-in benchmark workloads: fixed prompt sets, versioned so results stay comparable.

Changing a prompt changes what is measured, so any edit to a workload must bump
its ``version``. Two reports are comparable only if workload ids *and* versions
match.
"""

import base64
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict

from antar.core.errors import CapabilityNotSupportedError
from antar.core.types import Modality
from antar.inference.types import ImageInput


class BenchmarkPrompt(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    image: str | None = None


class Workload(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str
    modality: Modality
    version: str
    prompts: tuple[BenchmarkPrompt, ...]
    # "json": each response is checked for being parseable JSON. That is a
    # mechanical validity check, not a quality score.
    check: Literal["json"] | None = None


def _prompt(prompt_id: str, text: str, image: str | None = None) -> BenchmarkPrompt:
    return BenchmarkPrompt(id=prompt_id, text=text, image=image)


WORKLOADS: tuple[Workload, ...] = (
    Workload(
        id="general_qa",
        name="General question answering",
        description="Short factual and explanatory questions.",
        modality=Modality.TEXT,
        version="1",
        prompts=(
            _prompt("photosynthesis", "Explain photosynthesis in two sentences."),
            _prompt("tcp-udp", "What is the difference between TCP and UDP?"),
            _prompt("seasons", "Why does the Earth have seasons?"),
            _prompt("compound-interest", "What is compound interest? Give a short example."),
        ),
    ),
    Workload(
        id="code_generation",
        name="Code generation",
        description="Small, self-contained programming tasks.",
        modality=Modality.TEXT,
        version="1",
        prompts=(
            _prompt("fizzbuzz", "Write a Python function that prints FizzBuzz from 1 to n."),
            _prompt("binary-search", "Write a Python function for binary search on a sorted list."),
            _prompt(
                "debounce", "Write a JavaScript debounce function with a wait in milliseconds."
            ),
            _prompt(
                "sql-top", "Write a SQL query returning the five customers with the most orders."
            ),
        ),
    ),
    Workload(
        id="structured_json",
        name="Structured JSON generation",
        description="Requests that must be answered with a single JSON document.",
        modality=Modality.TEXT,
        version="1",
        check="json",
        prompts=(
            _prompt(
                "person",
                'Return only a JSON object with keys "name", "age" and "city" for a fictional '
                "person. No other text.",
            ),
            _prompt(
                "planets",
                "Return only a JSON array of the four inner planets, each an object with "
                '"name" and "order". No other text.',
            ),
            _prompt(
                "extract",
                'Extract the fields from: "Order 4521 shipped to Lisbon on 2026-03-14". Return '
                'only JSON with keys "order_id", "city" and "date". No other text.',
            ),
        ),
    ),
    Workload(
        id="vision_basic",
        name="Basic image understanding",
        description="Simple synthetic images. Responses need manual review; no score is computed.",
        modality=Modality.VISION,
        version="1",
        prompts=(
            _prompt("shapes", "List the shapes in this image and their colors.", "shapes.png"),
            _prompt(
                "bar-chart",
                "How many bars are in this chart, and which color is the tallest bar?",
                "bar-chart.png",
            ),
            _prompt("traffic-light", "Describe this image in one sentence.", "traffic-light.png"),
        ),
    ),
)


def get_workload(workload_id: str) -> Workload:
    workload = next((item for item in WORKLOADS if item.id == workload_id), None)
    if workload is None:
        known = ", ".join(item.id for item in WORKLOADS)
        raise CapabilityNotSupportedError(f"Unknown workload '{workload_id}'. Available: {known}.")
    return workload


def load_image(name: str) -> ImageInput:
    """Load a bundled sample image (see assets/LICENSE.md)."""
    data = resources.files("antar.benchmarking").joinpath("assets", name).read_bytes()
    return ImageInput(media_type="image/png", data_base64=base64.b64encode(data).decode("ascii"))
