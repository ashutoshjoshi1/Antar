"""GPU statistics for the AMD host, read from ``amd-smi`` over SSH.

``amd-smi static --json`` and ``amd-smi metric --json`` are documented commands
(AMD SMI CLI reference, checked 2026-11-18), but the reference does **not**
document the JSON key names. The parser below therefore looks values up
tolerantly and treats anything it cannot find as unavailable — never as zero.
The key names it tries (``asic.market_name``, ``vram.size``,
``mem_usage.used_vram``, ``usage.gfx_activity``, ``temperature.hotspot``,
``power.socket_power``) come from the field names in amd-smi's human-readable
output and **have not been confirmed against a real host**. Every sample
records which values were missing, so a wrong guess shows up as "unavailable"
with a reason rather than as a wrong number.

These are device-level readings for the whole GPU. They say nothing about a
single model or request.
"""

import asyncio
import json
import math
import time
from collections.abc import Callable

from antar.backends.amd_cloud.ssh import RemoteRunner
from antar.core.errors import BackendUnavailableError
from antar.hardware.gpu import GpuReading, GpuSample
from antar.hardware.telemetry import Unavailable

_SEPARATOR = "@@ANTAR-SECTION@@"
# One round trip per sample. Each command may fail without stopping the others.
GPU_COMMAND = (
    f"amd-smi static --json 2>/dev/null; echo '{_SEPARATOR}'; "
    f"amd-smi metric --json 2>/dev/null; echo '{_SEPARATOR}'; "
    "amd-smi version --json 2>/dev/null"
)

_BYTES = {"b": 1, "kb": 1000, "mb": 1000**2, "gb": 1000**3, "kib": 1024, "mib": 1024**2}
_BYTES["gib"] = 1024**3


def _lower(value: object) -> dict[str, object]:
    return (
        {str(key).lower(): item for key, item in value.items()} if isinstance(value, dict) else {}
    )


def _path(source: object, *keys: str) -> object:
    current = source
    for key in keys:
        current = _lower(current).get(key)
        if current is None:
            return None
    return current


def _number(value: object) -> tuple[float, str | None] | None:
    """A reading as (value, unit). Accepts ``{"value": 1, "unit": "W"}`` or a bare number."""
    unit: str | None = None
    if isinstance(value, dict):
        mapping = _lower(value)
        raw_unit = mapping.get("unit")
        unit = raw_unit.lower() if isinstance(raw_unit, str) else None
        value = mapping.get("value")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(value):
        return None
    return float(value), unit


def _plain(value: object) -> float | None:
    number = _number(value)
    return number[0] if number and number[0] >= 0 else None


def _memory(value: object) -> int | None:
    number = _number(value)
    if number is None or number[0] < 0:
        return None
    # amd-smi prints memory in MB in its human-readable output; a unit, when given, wins.
    factor = _BYTES.get(number[1] or "mb")
    return round(number[0] * factor) if factor else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value and value.upper() != "N/A" else None


def _devices(document: object) -> list[dict[str, object]]:
    """amd-smi prints either a list of GPUs or an object wrapping one."""
    if isinstance(document, dict):
        document = _lower(document).get("gpu_data")
    return (
        [item for item in document if isinstance(item, dict)] if isinstance(document, list) else []
    )


def _load(section: str) -> object:
    try:
        return json.loads(section)
    except (ValueError, RecursionError):
        return None


def parse_gpu_sample(output: str) -> GpuSample:
    """Build a sample from the output of ``GPU_COMMAND``."""
    sections = [part.strip() for part in output.split(_SEPARATOR)]
    sections += [""] * (3 - len(sections))
    static, metric, version = (_load(section) for section in sections[:3])
    gaps: list[Unavailable] = []
    if static is None and metric is None:
        return GpuSample(
            unavailable=(
                Unavailable(
                    metric="gpu",
                    reason="amd-smi returned no JSON. Is it installed and on the SSH user's PATH?",
                ),
            )
        )

    by_index: dict[int, dict[str, object]] = {}
    for kind, document in (("static", static), ("metric", metric)):
        for position, device in enumerate(_devices(document)):
            index = _lower(device).get("gpu")
            key = index if isinstance(index, int) and not isinstance(index, bool) else position
            by_index.setdefault(key, {})[kind] = device

    readings: list[GpuReading] = []
    for index in sorted(by_index):
        info, live = by_index[index].get("static"), by_index[index].get("metric")
        reading = GpuReading(
            index=index,
            name=_text(_path(info, "asic", "market_name")),
            memory_total_bytes=_memory(_path(info, "vram", "size"))
            or _memory(_path(live, "mem_usage", "total_vram")),
            memory_used_bytes=_memory(_path(live, "mem_usage", "used_vram")),
            utilization_percent=_plain(_path(live, "usage", "gfx_activity")),
            temperature_celsius=_plain(_path(live, "temperature", "hotspot"))
            or _plain(_path(live, "temperature", "edge")),
            power_watts=_plain(_path(live, "power", "socket_power")),
        )
        readings.append(reading)
        gaps.extend(
            Unavailable(
                metric=f"gpu{index}.{field}",
                reason="amd-smi did not report this value in the form Antar reads.",
            )
            for field, value in reading.model_dump(exclude={"index"}).items()
            if value is None
        )

    first_static = next(iter(_devices(static)), None)
    versions = _devices(version) or ([version] if isinstance(version, dict) else [])
    first_version = versions[0] if versions else None
    return GpuSample(
        gpus=tuple(readings),
        driver_version=_text(_path(first_static, "driver", "version")),
        rocm_version=_text(_path(first_version, "rocm_version")),
        amd_smi_version=_text(_path(first_version, "tool")),
        unavailable=tuple(gaps),
    )


class GpuMonitor:
    """Samples the remote GPUs, never more often than the configured interval."""

    def __init__(
        self,
        runner: RemoteRunner,
        *,
        min_interval_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._runner = runner
        self._min_interval = min_interval_seconds
        self._clock = clock
        self._last: GpuSample | None = None
        self._last_at: float | None = None
        self._lock = asyncio.Lock()

    @property
    def interval_seconds(self) -> float:
        return self._min_interval

    async def sample(self) -> GpuSample:
        """A fresh sample, or the previous one if it is younger than the interval.

        A host that cannot be reached is a sample with nothing in it and the
        reason attached; it is never an exception and never zeros.
        """
        async with self._lock:
            now = self._clock()
            if (
                self._last is not None
                and self._last_at is not None
                and now - self._last_at < self._min_interval
            ):
                return self._last
            try:
                result = await self._runner.run(GPU_COMMAND)
                sample = parse_gpu_sample(result.stdout)
            except BackendUnavailableError as exc:
                sample = GpuSample(unavailable=(Unavailable(metric="gpu", reason=str(exc)),))
            self._last, self._last_at = sample, now
            return sample
