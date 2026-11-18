"""GPU readings, preflight, memory sizing, and cost arithmetic for the AMD host.

The amd-smi documents below are **synthetic**: they follow the shape Antar's
parser expects, which has not been confirmed against real hardware. They test
the parser's behaviour, and are not recorded measurements.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from antar.backends.amd_cloud.amd_smi import GPU_COMMAND, GpuMonitor, parse_gpu_sample
from antar.backends.amd_cloud.config import CloudCostSettings
from antar.backends.amd_cloud.cost import CloudSession, CloudSessionStore, estimate_cost
from antar.backends.amd_cloud.feasibility import (
    GIB,
    FeasibilityRequest,
    estimate_feasibility,
    kv_cache_bytes_per_token,
)
from antar.backends.amd_cloud.preflight import (
    PREFLIGHT_COMMAND,
    PREFLIGHT_SCRIPT,
    parse_preflight,
    run_preflight,
)
from antar.core.errors import BackendRequestError
from antar.models.catalog import KNOWN_MODELS, find_known_model
from tests.conftest import FakeRunner

SEPARATOR = "@@ANTAR-SECTION@@"


def _reading(value: object, unit: str) -> dict[str, object]:
    return {"value": value, "unit": unit}


def _amd_smi(gpus: int = 2, *, wrapped: bool = False, power: object = 310) -> str:
    static = [
        {
            "gpu": index,
            "asic": {"market_name": "AMD Instinct MI300X"},
            "vram": {"size": _reading(196288, "MB")},
            "driver": {"name": "amdgpu", "version": "6.12.12"},
        }
        for index in range(gpus)
    ]
    metric = [
        {
            "gpu": index,
            "usage": {"gfx_activity": _reading(40 + index, "%")},
            "power": {"socket_power": _reading(power, "W") if power != "N/A" else "N/A"},
            "temperature": {"hotspot": _reading(61, "C")},
            "mem_usage": {"used_vram": _reading(70000, "MB")},
        }
        for index in range(gpus)
    ]
    version = {"tool": "26.2.0", "rocm_version": "7.1.0"}
    documents: list[object] = [static, metric, version]
    if wrapped:
        documents = [{"gpu_data": static}, {"gpu_data": metric}, version]
    return f"\n{SEPARATOR}\n".join(json.dumps(document) for document in documents)


@pytest.mark.parametrize("wrapped", [False, True])
def test_gpu_readings_are_parsed_per_device(wrapped: bool) -> None:
    sample = parse_gpu_sample(_amd_smi(wrapped=wrapped))

    assert len(sample.gpus) == 2
    first = sample.gpus[0]
    assert first.name == "AMD Instinct MI300X"
    assert first.memory_total_bytes == 196288 * 1000**2
    assert first.memory_used_bytes == 70000 * 1000**2
    assert (first.utilization_percent, sample.gpus[1].utilization_percent) == (40, 41)
    assert (first.temperature_celsius, first.power_watts) == (61, 310)
    assert (sample.driver_version, sample.rocm_version) == ("6.12.12", "7.1.0")
    assert sample.unavailable == ()


def test_a_value_amd_smi_marks_not_available_stays_unavailable_not_zero() -> None:
    sample = parse_gpu_sample(_amd_smi(gpus=1, power="N/A"))

    assert sample.gpus[0].power_watts is None
    assert [gap.metric for gap in sample.unavailable] == ["gpu0.power_watts"]


def test_unrecognized_key_names_produce_gaps_rather_than_guesses() -> None:
    document = json.dumps([{"gpu": 0, "something_new": {"watts": 5}}])

    sample = parse_gpu_sample(f"{document}\n{SEPARATOR}\n{document}\n{SEPARATOR}\n")

    (gpu,) = sample.gpus
    assert gpu.model_dump(exclude={"index"}) == dict.fromkeys(
        (
            "name",
            "memory_total_bytes",
            "memory_used_bytes",
            "utilization_percent",
            "temperature_celsius",
            "power_watts",
        )
    )
    assert len(sample.unavailable) == 6


def test_missing_amd_smi_is_reported_with_a_reason() -> None:
    sample = parse_gpu_sample(f"\n{SEPARATOR}\n\n{SEPARATOR}\n")

    assert sample.gpus == ()
    assert "amd-smi returned no JSON" in sample.unavailable[0].reason


def test_the_monitor_does_not_poll_faster_than_its_interval() -> None:
    now = [0.0]
    runner = FakeRunner({GPU_COMMAND: _amd_smi()})
    monitor = GpuMonitor(runner, min_interval_seconds=10, clock=lambda: now[0])

    async def sample_at(*moments: float) -> None:
        for moment in moments:
            now[0] = moment
            await monitor.sample()

    asyncio.run(sample_at(0, 3, 9.9, 10, 15))

    assert runner.commands == [GPU_COMMAND, GPU_COMMAND]


def test_a_disconnected_host_yields_an_empty_sample_with_the_reason() -> None:
    monitor = GpuMonitor(
        FakeRunner(error="SSH to the AMD host failed: timed out"), min_interval_seconds=2
    )

    sample = asyncio.run(monitor.sample())

    assert sample.gpus == ()
    assert "timed out" in sample.unavailable[0].reason


# --- preflight -------------------------------------------------------------------------

PREFLIGHT_OUTPUT = "\n".join(
    [
        "noise the shell printed",
        "ANTAR_CHECK\tos\tpass\tUbuntu 24.04\t",
        "ANTAR_CHECK\tdocker_permissions\tfail\tneeds sudo\tsudo usermod -aG docker $USER",
        "ANTAR_CHECK\timage\twarn\tnot pulled yet\tdocker pull the image",
        "ANTAR_CHECK\tbogus\tmaybe\tunknown status\t",
        "ANTAR_FACT\tgpu_count\t2",
        "ANTAR_FACT\tgpu_model\tAMD Instinct MI300X",
    ]
)


def test_preflight_results_carry_specific_failures_and_remediation() -> None:
    report = parse_preflight(PREFLIGHT_OUTPUT)

    assert [(check.id, check.status) for check in report.checks] == [
        ("os", "pass"),
        ("docker_permissions", "fail"),
        ("image", "warn"),
    ]
    assert report.checks[1].remediation == "sudo usermod -aG docker $USER"
    assert report.checks[0].remediation is None
    assert report.facts == {"gpu_count": "2", "gpu_model": "AMD Instinct MI300X"}
    assert report.ok is False


def test_preflight_pipes_the_repository_script_and_nothing_else() -> None:
    runner = FakeRunner({PREFLIGHT_COMMAND: PREFLIGHT_OUTPUT})

    report = asyncio.run(run_preflight(runner))

    assert runner.commands == [PREFLIGHT_COMMAND]
    assert runner.stdin == [PREFLIGHT_SCRIPT.read_bytes()]
    assert len(report.checks) == 3


def test_a_preflight_that_prints_nothing_is_an_error_not_a_pass(tmp_path: Path) -> None:
    script = tmp_path / "check.sh"
    script.write_text("#!/bin/sh\n")

    with pytest.raises(BackendRequestError, match="no results"):
        asyncio.run(run_preflight(FakeRunner(), script))


# --- memory feasibility ----------------------------------------------------------------

MI300X_BYTES = 192 * GIB


def test_kv_cache_size_follows_the_published_architecture() -> None:
    model = find_known_model("Qwen/Qwen3-32B")
    assert model is not None

    # 2 tensors x 64 layers x 8 KV heads x (5120 / 64) dims x 2 bytes (BF16)
    assert kv_cache_bytes_per_token(model) == 2 * 64 * 8 * 80 * 2


def test_a_32b_model_fits_one_large_gpu_with_the_budget_itemized() -> None:
    model = find_known_model("Qwen/Qwen3-32B")
    assert model is not None

    estimate = estimate_feasibility(model, FeasibilityRequest(gpu_memory_bytes=MI300X_BYTES))

    assert estimate.verdict == "fits"
    assert estimate.weights_bytes == 65_524_328_560
    assert estimate.kv_cache_bytes == 163_840 * 40_960
    assert estimate.required_bytes == (
        estimate.weights_bytes + estimate.kv_cache_bytes + estimate.runtime_overhead_bytes
    )
    assert estimate.usable_bytes == round(MI300X_BYTES * 0.9)
    assert estimate.max_concurrency_at_full_context >= 1


def test_the_same_model_does_not_fit_a_small_gpu_until_more_are_used() -> None:
    model = find_known_model("Qwen/Qwen3-32B")
    assert model is not None
    small = 48 * GIB

    one = estimate_feasibility(model, FeasibilityRequest(gpu_memory_bytes=small))
    two = estimate_feasibility(model, FeasibilityRequest(gpu_memory_bytes=small, gpu_count=2))

    assert one.verdict == "does_not_fit"
    assert one.headroom_bytes < 0
    assert two.verdict in ("fits", "tight")
    assert any("tensor-parallel-size 2" in note for note in two.notes)


def test_concurrency_and_context_drive_the_cache_not_the_weights() -> None:
    model = find_known_model("Qwen/Qwen3-VL-8B-Instruct")
    assert model is not None
    request = FeasibilityRequest(gpu_memory_bytes=MI300X_BYTES, max_model_len=32768, concurrency=8)

    estimate = estimate_feasibility(model, request)

    assert estimate.kv_cache_bytes == estimate.kv_cache_bytes_per_token * 32768 * 8
    assert any("Image inputs" in note for note in estimate.notes)


def test_catalog_entries_are_internally_consistent() -> None:
    for model in KNOWN_MODELS:
        assert model.hidden_size % model.num_attention_heads == 0
        # BF16 weights are two bytes per parameter; files add only a little metadata.
        assert 2.0 <= model.weights_bytes / model.parameter_count < 2.01
        assert len(model.revision) == 40


# --- cost ------------------------------------------------------------------------------

START = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
DEFAULTS = CloudCostSettings()


def test_spending_is_elapsed_time_at_the_entered_price() -> None:
    session = CloudSession(hourly_price_usd=4.0, credit_balance_usd=100, instance_started_at=START)

    estimate = estimate_cost(session, DEFAULTS, now=START + timedelta(minutes=90))

    assert estimate.running is True
    assert estimate.elapsed_seconds == 5400
    assert estimate.estimated_spend_usd == pytest.approx(6.0)
    assert estimate.estimated_remaining_usd == pytest.approx(94.0)
    assert estimate.estimated_hours_remaining == pytest.approx(23.5)
    assert any("bills until you stop it" in warning for warning in estimate.warnings)


def test_without_a_price_nothing_is_estimated() -> None:
    estimate = estimate_cost(CloudSession(instance_started_at=START), DEFAULTS, now=START)

    assert estimate.estimated_spend_usd is None
    assert estimate.estimated_remaining_usd is None
    assert any("No hourly price" in warning for warning in estimate.warnings)


def test_a_declared_stop_freezes_the_clock() -> None:
    session = CloudSession(
        hourly_price_usd=2.0,
        instance_started_at=START,
        instance_stopped_at=START + timedelta(hours=1),
    )

    estimate = estimate_cost(session, DEFAULTS, now=START + timedelta(days=3))

    assert estimate.running is False
    assert estimate.estimated_spend_usd == pytest.approx(2.0)


@pytest.mark.parametrize(("hours", "expected"), [(8.5, "passed 80%"), (11, "reached the entered")])
def test_warnings_as_the_credit_runs_out(hours: float, expected: str) -> None:
    session = CloudSession(hourly_price_usd=10, credit_balance_usd=100, instance_started_at=START)

    estimate = estimate_cost(session, DEFAULTS, now=START + timedelta(hours=hours))

    assert any(expected in warning for warning in estimate.warnings)


def test_impossible_session_times_are_rejected() -> None:
    with pytest.raises(ValidationError, match="before it started"):
        CloudSession(instance_started_at=START, instance_stopped_at=START - timedelta(hours=1))
    with pytest.raises(ValidationError, match="timezone"):
        CloudSession(instance_started_at=datetime(2026, 11, 18, 12, 0))


def test_the_session_store_starts_from_configured_defaults_and_persists(tmp_path: Path) -> None:
    store = CloudSessionStore(tmp_path / "cloud", CloudCostSettings(hourly_price_usd=3.5))

    assert store.load() == CloudSession(hourly_price_usd=3.5)
    store.save(CloudSession(hourly_price_usd=5, instance_started_at=START))

    assert store.load().hourly_price_usd == 5
    assert store.load().instance_started_at == START
