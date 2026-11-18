"""Automatic scoring of a response against a reference answer.

Each method is mechanical and narrow on purpose. A score says "the response
matched the reference by this rule"; it is not a general judgement of quality.
Free-text and descriptive answers are not scored here at all — those are
reviewed by a person (``RunRecord.manual_score``).

Running model-written code is opt-in. ``python_tests`` executes the response
in a separate Python process with a time limit. That contains mistakes, not
malice: it is **not** a security sandbox, which is why it is off by default.
The code runs as the current user with file and network access, and because the
tests are tallied in the same process, code written to cheat could report a
pass it did not earn. Treat a unit-test score as trustworthy only for a model
that is not trying to game it.
"""

import contextlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ScoreMethod = Literal["exact", "number", "keywords", "json_fields", "python_tests"]
JsonType = Literal["string", "number", "integer", "boolean", "array", "object"]
JsonValue = str | int | float | bool

_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_FENCE = re.compile(r"```[^\n]*\n(.*?)(?:```|\Z)", re.DOTALL)
_CODE_TIMEOUT_SECONDS = 10
_RESULT_MARKER = "@@ANTAR-RESULT@@"
_MAX_OUTPUT_CHARS = 10_000

_HARNESS = f"""
import contextlib, io, json, resource, sys
resource.setrlimit(resource.RLIMIT_CPU, ({_CODE_TIMEOUT_SECONDS}, {_CODE_TIMEOUT_SECONDS}))
job = json.loads(sys.stdin.read())
namespace = {{}}
passed = 0
with contextlib.redirect_stdout(io.StringIO()):
    try:
        exec(job["code"], namespace)
        loaded = True
    except BaseException:
        loaded = False
    if loaded:
        for test in job["tests"]:
            try:
                exec(test, namespace)
                passed += 1
            except BaseException:
                pass
print("{_RESULT_MARKER}" + job["nonce"] + json.dumps({{"passed": passed}}))
"""


class Expectation(BaseModel):
    """The reference for one prompt and the rule used to compare a response with it."""

    model_config = ConfigDict(frozen=True)

    method: ScoreMethod
    answer: str | None = Field(default=None, description="For 'exact'.")
    number: float | None = Field(default=None, description="For 'number'.")
    keywords: tuple[str, ...] = Field(default=(), description="For 'keywords'.")
    fields: dict[str, JsonType] = Field(default={}, description="For 'json_fields'.")
    values: dict[str, JsonValue] = Field(
        default={}, description="For 'json_fields': fields that must equal a specific value."
    )
    tests: tuple[str, ...] = Field(default=(), description="For 'python_tests': assert lines.")

    @model_validator(mode="after")
    def _has_its_reference(self) -> "Expectation":
        present = {
            "exact": self.answer is not None,
            "number": self.number is not None,
            "keywords": bool(self.keywords),
            "json_fields": bool(self.fields),
            "python_tests": bool(self.tests),
        }
        if not present[self.method]:
            raise ValueError(f"method '{self.method}' is missing its reference")
        return self


class Score(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float | None = Field(
        default=None, ge=0, le=1, description="None when the response was not scored."
    )
    method: ScoreMethod
    detail: str


def strip_code_fence(text: str) -> str:
    """The contents of the first Markdown code fence, or the text itself if there is none."""
    match = _FENCE.search(text)
    return (match.group(1) if match else text).strip()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().strip("\"'`*.!").strip().casefold()


def _exact(expected: str, response: str) -> Score:
    matched = _normalize(response) == _normalize(expected)
    return Score(
        value=float(matched),
        method="exact",
        detail="Matched the reference." if matched else f"Expected '{expected}'.",
    )


def _number(expected: float, response: str) -> Score:
    found = _NUMBER.findall(response)
    if not found:
        return Score(value=0.0, method="number", detail="The response contains no number.")
    # The last number is taken as the answer, so shown working does not count against it.
    actual = float(found[-1].replace(",", ""))
    matched = abs(actual - expected) <= 1e-6 * max(1.0, abs(expected))
    return Score(
        value=float(matched),
        method="number",
        detail="Matched the reference." if matched else f"Expected {expected:g}, got {actual:g}.",
    )


def _keywords(keywords: tuple[str, ...], response: str) -> Score:
    text = response.casefold()
    missing = [word for word in keywords if word.casefold() not in text]
    found = len(keywords) - len(missing)
    detail = f"{found} of {len(keywords)} reference terms present."
    if missing:
        detail += f" Missing: {', '.join(missing)}."
    return Score(value=found / len(keywords), method="keywords", detail=detail)


def _is_type(value: object, expected: JsonType) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    return isinstance(value, list if expected == "array" else dict)


def _json_fields(expectation: Expectation, response: str) -> Score:
    try:
        document = json.loads(strip_code_fence(response))
    except ValueError:
        return Score(value=0.0, method="json_fields", detail="The response is not valid JSON.")
    if not isinstance(document, dict):
        return Score(value=0.0, method="json_fields", detail="The response is not a JSON object.")
    problems = [
        f"'{key}' is missing or not {kind}"
        for key, kind in expectation.fields.items()
        if key not in document or not _is_type(document[key], kind)
    ]
    problems += [
        f"'{key}' should be {value!r}"
        for key, value in expectation.values.items()
        if document.get(key) != value
    ]
    return Score(
        value=0.0 if problems else 1.0,
        method="json_fields",
        detail="; ".join(problems) + "." if problems else "All required fields are valid.",
    )


def _python_tests(tests: tuple[str, ...], response: str) -> Score:
    nonce = secrets.token_hex(16)
    job = json.dumps({"code": strip_code_fence(response), "tests": tests, "nonce": nonce})
    with tempfile.TemporaryDirectory() as workdir:
        process = subprocess.Popen(
            [sys.executable, "-I", "-c", _HARNESS],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=workdir,
            env={},
            start_new_session=True,
        )
        try:
            stdout, _ = process.communicate(job, timeout=_CODE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return Score(value=0.0, method="python_tests", detail="The code timed out.")
        finally:
            # Kill the whole process group, so nothing the code started outlives the test.
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    _, marker, result = stdout[-_MAX_OUTPUT_CHARS:].rpartition(_RESULT_MARKER + nonce)
    try:
        passed = int(json.loads(result)["passed"]) if marker else 0
    except (ValueError, KeyError, TypeError):
        passed = 0
    if not 0 <= passed <= len(tests):
        passed = 0
    return Score(
        value=passed / len(tests),
        method="python_tests",
        detail=f"{passed} of {len(tests)} unit tests passed.",
    )


def score_response(
    expectation: Expectation, response: str, *, allow_code_execution: bool = False
) -> Score:
    if expectation.method == "exact" and expectation.answer is not None:
        return _exact(expectation.answer, response)
    if expectation.method == "number" and expectation.number is not None:
        return _number(expectation.number, response)
    if expectation.method == "keywords":
        return _keywords(expectation.keywords, response)
    if expectation.method == "json_fields":
        return _json_fields(expectation, response)
    if not allow_code_execution:
        return Score(
            method="python_tests",
            detail="Not scored: running model-written code was not enabled for this run.",
        )
    return _python_tests(expectation.tests, response)
