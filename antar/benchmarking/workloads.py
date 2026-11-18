"""Built-in benchmark workloads: fixed prompt sets, versioned so results stay comparable.

Changing a prompt changes what is measured, so any edit to a workload must bump
its ``version``. Two reports are comparable only if workload ids *and* versions
match.
"""

import base64
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from antar.core.errors import CapabilityNotSupportedError
from antar.core.types import Modality
from antar.evaluation.scoring import Expectation
from antar.inference.types import ImageInput

# Provenance of the scored workloads. The prompts and references were written for Antar;
# each reference is either a checkable fact or follows from the bundled image generator.
_AUTHORED = "Written for Antar. No third-party content."
_LICENSE = "CC0-1.0"


class BenchmarkPrompt(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    image: str | None = None
    expect: Expectation | None = Field(
        default=None, description="Reference and scoring rule. None: reviewed by a person."
    )


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
    license: str | None = Field(default=None, description="SPDX id of the prompt set.")
    provenance: str | None = None

    @property
    def scored(self) -> bool:
        return any(prompt.expect is not None for prompt in self.prompts)


def _prompt(prompt_id: str, text: str, image: str | None = None) -> BenchmarkPrompt:
    return BenchmarkPrompt(id=prompt_id, text=text, image=image)


def _exact(prompt_id: str, text: str, answer: str, image: str | None = None) -> BenchmarkPrompt:
    expect = Expectation(method="exact", answer=answer)
    return BenchmarkPrompt(id=prompt_id, text=text, image=image, expect=expect)


def _number(prompt_id: str, text: str, number: float, image: str | None = None) -> BenchmarkPrompt:
    expect = Expectation(method="number", number=number)
    return BenchmarkPrompt(id=prompt_id, text=text, image=image, expect=expect)


def _code(prompt_id: str, text: str, *tests: str) -> BenchmarkPrompt:
    return BenchmarkPrompt(
        id=prompt_id,
        text=f"{text} Reply with only the Python code.",
        expect=Expectation(method="python_tests", tests=tests),
    )


_ONE_WORD = " Answer with one word."
_ONLY_NUMBER = " Answer with only the number."


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
    Workload(
        id="qa_exact",
        name="Factual questions (exact answers)",
        description="Questions with one short, checkable answer. Scored by exact match.",
        modality=Modality.TEXT,
        version="1",
        license=_LICENSE,
        provenance=_AUTHORED,
        prompts=(
            _exact(
                "gold", "What is the chemical symbol for gold? Answer with only the symbol.", "Au"
            ),
            _exact("japan", "What is the capital of Japan?" + _ONE_WORD, "Tokyo"),
            _exact(
                "planet", "Which planet in the Solar System is the largest?" + _ONE_WORD, "Jupiter"
            ),
            _number("apollo", "In which year did Apollo 11 land on the Moon?" + _ONLY_NUMBER, 1969),
            _number("hexagon", "How many sides does a hexagon have?" + _ONLY_NUMBER, 6),
            _number("continents", "How many continents are there on Earth?" + _ONLY_NUMBER, 7),
        ),
    ),
    Workload(
        id="reasoning_basic",
        name="Basic reasoning",
        description="Short arithmetic and logic problems. Scored on the final answer.",
        modality=Modality.TEXT,
        version="1",
        license=_LICENSE,
        provenance=_AUTHORED,
        prompts=(
            _number("multiply", "What is 17 multiplied by 23?" + _ONLY_NUMBER, 391),
            _number("percent", "What is 15 percent of 240?" + _ONLY_NUMBER, 36),
            _number(
                "distance",
                "A train travels at 60 km/h for 2.5 hours. How many kilometres does it cover?"
                + _ONLY_NUMBER,
                150,
            ),
            _number(
                "sequence",
                "What is the next number in the sequence 2, 6, 12, 20, 30?" + _ONLY_NUMBER,
                42,
            ),
            _number(
                "apples",
                "Tom has three times as many apples as Ana. Together they have 24. How many "
                "apples does Tom have?" + _ONLY_NUMBER,
                18,
            ),
            _exact(
                "syllogism",
                "All bloops are razzies. All razzies are lazzies. Are all bloops lazzies? "
                "Answer with only yes or no.",
                "yes",
            ),
        ),
    ),
    Workload(
        id="json_schema",
        name="Structured JSON (schema checked)",
        description="JSON answers checked for required fields, types, and extracted values.",
        modality=Modality.TEXT,
        version="1",
        license=_LICENSE,
        provenance=_AUTHORED,
        prompts=(
            BenchmarkPrompt(
                id="order",
                text='Extract the fields from: "Order 4521 shipped to Lisbon on 2026-03-14". '
                'Return only a JSON object with keys "order_id" (integer), "city" (string) and '
                '"date" (string, YYYY-MM-DD). No other text.',
                expect=Expectation(
                    method="json_fields",
                    fields={"order_id": "integer", "city": "string", "date": "string"},
                    values={"order_id": 4521, "city": "Lisbon", "date": "2026-03-14"},
                ),
            ),
            BenchmarkPrompt(
                id="sensor",
                text='Extract the fields from: "Sensor T7 read 21.5 degrees and is online". '
                'Return only a JSON object with keys "sensor" (string), "temperature" (number) '
                'and "online" (boolean). No other text.',
                expect=Expectation(
                    method="json_fields",
                    fields={"sensor": "string", "temperature": "number", "online": "boolean"},
                    values={"sensor": "T7", "temperature": 21.5, "online": True},
                ),
            ),
            BenchmarkPrompt(
                id="profile",
                text='Return only a JSON object describing a fictional person, with keys "name" '
                '(string), "age" (integer) and "languages" (array of strings). No other text.',
                expect=Expectation(
                    method="json_fields",
                    fields={"name": "string", "age": "integer", "languages": "array"},
                ),
            ),
        ),
    ),
    Workload(
        id="code_tests",
        name="Code generation (unit tested)",
        description=(
            "Python functions checked by unit tests. Scored only when running model-written "
            "code is enabled for the run."
        ),
        modality=Modality.TEXT,
        version="1",
        license=_LICENSE,
        provenance=_AUTHORED,
        prompts=(
            _code(
                "palindrome",
                "Write a Python function is_palindrome(s) that returns True if the string s "
                "reads the same forwards and backwards, ignoring case and any character that "
                "is not a letter or digit.",
                "assert is_palindrome('A man, a plan, a canal: Panama') is True",
                "assert is_palindrome('antar') is False",
                "assert is_palindrome('') is True",
            ),
            _code(
                "fibonacci",
                "Write a Python function fibonacci(n) that returns the n-th Fibonacci number, "
                "where fibonacci(0) is 0 and fibonacci(1) is 1.",
                "assert fibonacci(0) == 0",
                "assert fibonacci(1) == 1",
                "assert fibonacci(10) == 55",
                "assert fibonacci(30) == 832040",
            ),
            _code(
                "merge",
                "Write a Python function merge_sorted(a, b) that merges two sorted lists of "
                "integers into one sorted list.",
                "assert merge_sorted([1, 4, 9], [2, 3, 10]) == [1, 2, 3, 4, 9, 10]",
                "assert merge_sorted([], [5]) == [5]",
                "assert merge_sorted([2, 2], [2]) == [2, 2, 2]",
            ),
        ),
    ),
    Workload(
        id="vision_reference",
        name="Image understanding (reference answers)",
        description=(
            "Questions about synthetic images and a simple diagram, each with one checkable answer."
        ),
        modality=Modality.VISION,
        version="1",
        license=_LICENSE,
        provenance=_AUTHORED + " Images come from scripts/generate_benchmark_images.py.",
        prompts=(
            _number(
                "bar-count", "How many bars are in this chart?" + _ONLY_NUMBER, 4, "bar-chart.png"
            ),
            _exact(
                "bar-tallest",
                "What colour is the tallest bar in this chart?" + _ONE_WORD,
                "red",
                "bar-chart.png",
            ),
            _exact("square-colour", "What colour is the square?" + _ONE_WORD, "blue", "shapes.png"),
            _exact(
                "top-lamp",
                "What colour is the top lamp of this traffic light?" + _ONE_WORD,
                "red",
                "traffic-light.png",
            ),
            _number(
                "diagram-boxes",
                "How many boxes are in this diagram?" + _ONLY_NUMBER,
                3,
                "diagram.png",
            ),
            _exact(
                "diagram-flow",
                "In this diagram, which box does the arrow leaving the box labelled CPU point "
                "to? Answer with only the label.",
                "GPU",
                "diagram.png",
            ),
        ),
    ),
    Workload(
        id="ocr_basic",
        name="Text in images (OCR)",
        description="Reading printed text from a synthetic document image.",
        modality=Modality.VISION,
        version="1",
        license=_LICENSE,
        provenance=_AUTHORED + " Images come from scripts/generate_benchmark_images.py.",
        prompts=(
            _number(
                "invoice-number",
                "What is the invoice number in this document?" + _ONLY_NUMBER,
                4821,
                "document.png",
            ),
            _exact(
                "invoice-date",
                "What is the date in this document? Answer with only the date as written.",
                "2026-03-14",
                "document.png",
            ),
            _number(
                "invoice-total",
                "What is the total in this document?" + _ONLY_NUMBER,
                137.5,
                "document.png",
            ),
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
