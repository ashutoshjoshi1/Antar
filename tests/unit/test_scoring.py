"""Automatic scoring rules: what counts as a match, and what is deliberately not scored."""

import pytest
from pydantic import ValidationError

from antar.evaluation.scoring import Expectation, score_response, strip_code_fence


@pytest.mark.parametrize("response", ["Tokyo", " tokyo. ", '"Tokyo"', "**Tokyo**"])
def test_exact_match_ignores_case_and_decoration(response: str) -> None:
    assert score_response(Expectation(method="exact", answer="Tokyo"), response).value == 1.0


def test_exact_match_does_not_accept_an_answer_buried_in_a_sentence() -> None:
    score = score_response(Expectation(method="exact", answer="Tokyo"), "The capital is Tokyo")

    assert score.value == 0.0
    assert "Expected 'Tokyo'" in score.detail


@pytest.mark.parametrize(
    ("response", "expected"),
    [("391", 1.0), ("17 x 23 = 391", 1.0), ("1,969", 0.0), ("about 390", 0.0), ("none", 0.0)],
)
def test_number_scoring_uses_the_final_number(response: str, expected: float) -> None:
    assert score_response(Expectation(method="number", number=391), response).value == expected


def test_number_scoring_reads_thousands_separators_and_decimals() -> None:
    assert score_response(Expectation(method="number", number=1969), "1,969").value == 1.0
    assert score_response(Expectation(method="number", number=137.5), "137.50").value == 1.0


def test_keyword_scoring_is_the_share_of_reference_terms_found() -> None:
    expectation = Expectation(method="keywords", keywords=("circle", "square", "triangle"))

    score = score_response(expectation, "A red Circle and a blue square.")

    assert score.value == pytest.approx(2 / 3)
    assert "triangle" in score.detail


ORDER = Expectation(
    method="json_fields",
    fields={"order_id": "integer", "city": "string"},
    values={"order_id": 4521, "city": "Lisbon"},
)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ('{"order_id": 4521, "city": "Lisbon"}', 1.0),
        ('```json\n{"order_id": 4521, "city": "Lisbon", "extra": 1}\n```', 1.0),
        ('{"order_id": "4521", "city": "Lisbon"}', 0.0),
        ('{"order_id": 4521, "city": "Porto"}', 0.0),
        ('{"order_id": true, "city": "Lisbon"}', 0.0),
        ("[1, 2]", 0.0),
        ("Order 4521, Lisbon", 0.0),
    ],
)
def test_json_fields_check_types_and_extracted_values(response: str, expected: float) -> None:
    assert score_response(ORDER, response).value == expected


TESTS = Expectation(
    method="python_tests", tests=("assert double(2) == 4", "assert double(-1) == -2")
)


def test_code_is_not_run_unless_explicitly_allowed() -> None:
    score = score_response(TESTS, "def double(x):\n    return x * 2")

    assert score.value is None
    assert "was not enabled" in score.detail


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("```python\ndef double(x):\n    return x * 2\n```", 1.0),
        ("def double(x):\n    print('noise')\n    return abs(x) * 2", 0.5),
        ("def double(x):\n    raise SystemExit(0)", 0.0),
        ("this is not python", 0.0),
    ],
)
def test_unit_test_pass_rate_when_code_execution_is_allowed(code: str, expected: float) -> None:
    score = score_response(TESTS, code, allow_code_execution=True)

    assert score.value == expected
    assert "unit tests passed" in score.detail


def test_an_expectation_must_carry_the_reference_for_its_method() -> None:
    with pytest.raises(ValidationError, match="missing its reference"):
        Expectation(method="number", answer="42")


def test_code_fence_extraction_handles_an_unclosed_fence() -> None:
    assert strip_code_fence("Here:\n```python\nx = 1\n") == "x = 1"
    assert strip_code_fence("x = 1") == "x = 1"


def test_a_forged_result_line_does_not_earn_a_pass() -> None:
    forged = "import os\nos.write(1, b'@@ANTAR-RESULT@@{\"passed\": 2}\\n')\nos._exit(0)\n"

    assert score_response(TESTS, forged, allow_code_execution=True).value == 0.0
