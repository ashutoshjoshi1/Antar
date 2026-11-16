"""Live telemetry: only what the operating system actually lets this process read.

Anything that cannot be measured is returned as an ``Unavailable`` entry with
the reason, so callers can show "unavailable" instead of a made-up number.
"""

import os
import platform

import psutil
from pydantic import BaseModel, ConfigDict, Field

# psutil measures CPU use between calls; the first call only sets the baseline.
psutil.cpu_percent(interval=None)


class Unavailable(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: str
    reason: str


class ProcessMemory(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    pid: int
    rss_bytes: int = Field(ge=0)


class SystemTelemetry(BaseModel):
    model_config = ConfigDict(frozen=True)

    cpu_percent: float = Field(ge=0, description="System-wide, since the previous sample.")
    memory_total_bytes: int = Field(ge=0)
    memory_available_bytes: int = Field(ge=0)
    processes: tuple[ProcessMemory, ...] = ()
    unavailable: tuple[Unavailable, ...] = ()


def _static_gaps() -> list[Unavailable]:
    system = platform.system()
    if system == "Darwin":
        reason = "macOS exposes this only through privileged tools such as powermetrics."
    else:
        reason = "Not collected on this platform yet."
    return [
        Unavailable(metric="gpu_utilization", reason=reason),
        Unavailable(metric="gpu_memory_used", reason=reason),
        Unavailable(metric="power_draw", reason=reason),
    ]


def collect_telemetry(model_processes: tuple[tuple[str, int | None], ...] = ()) -> SystemTelemetry:
    """Sample the system. ``model_processes`` are (label, pid) pairs to inspect."""
    memory = psutil.virtual_memory()
    processes = [
        ProcessMemory(
            label="Antar API", pid=os.getpid(), rss_bytes=psutil.Process().memory_info().rss
        )
    ]
    gaps = _static_gaps()
    for label, pid in model_processes:
        metric = f"model_memory:{label}"
        if pid is None:
            gaps.append(Unavailable(metric=metric, reason="The backend did not report a process."))
            continue
        try:
            rss = psutil.Process(pid).memory_info().rss
        except psutil.AccessDenied:
            gaps.append(
                Unavailable(
                    metric=metric,
                    reason="The model server runs as another user; its memory is not readable.",
                )
            )
        except psutil.Error:
            gaps.append(
                Unavailable(metric=metric, reason="The model process is no longer running.")
            )
        else:
            processes.append(ProcessMemory(label=label, pid=pid, rss_bytes=rss))
    return SystemTelemetry(
        cpu_percent=psutil.cpu_percent(interval=None),
        memory_total_bytes=memory.total,
        memory_available_bytes=memory.available,
        processes=tuple(processes),
        unavailable=tuple(gaps),
    )
