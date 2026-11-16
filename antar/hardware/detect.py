"""Local hardware detection.

Everything here reports what was actually observed. When a probe fails or a
platform is not covered, the field is left empty rather than estimated.
"""

import json
import logging
import platform
import shutil
import socket
import subprocess
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

import psutil

from antar.hardware.profile import Accelerator, AcceleratorKind, HardwareProfile, RuntimeSupport

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT_SECONDS = 5.0


def _run(args: list[str]) -> str | None:
    """Run a fixed probe command, returning stdout or None if it is unusable."""
    executable = shutil.which(args[0])
    if executable is None:
        return None
    try:
        completed = subprocess.run(
            [executable, *args[1:]],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Hardware probe %s failed: %s", args[0], exc)
        return None
    return completed.stdout.strip()


def _is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


@lru_cache(maxsize=1)
def _cpu_model() -> str:
    system = platform.system()
    if system == "Darwin":
        brand = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if brand:
            return brand
    if system == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError as exc:
            logger.warning("Could not read /proc/cpuinfo: %s", exc)
    return platform.processor() or "unknown"


def parse_macos_displays(raw_json: str) -> tuple[Accelerator, ...]:
    """Parse ``system_profiler SPDisplaysDataType -json`` output into accelerators."""
    try:
        payload: Any = json.loads(raw_json)
    except json.JSONDecodeError:
        return ()
    entries = payload.get("SPDisplaysDataType") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return ()

    accelerators: list[Accelerator] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("sppci_model") or entry.get("_name")
        if not isinstance(name, str):
            continue
        cores = entry.get("sppci_cores")
        is_apple = "apple" in name.lower()
        accelerators.append(
            Accelerator(
                name=name,
                kind=AcceleratorKind.APPLE_GPU if is_apple else AcceleratorKind.OTHER,
                vendor="Apple" if is_apple else None,
                shares_system_memory=is_apple,
                cores=int(cores) if isinstance(cores, str) and cores.isdigit() else None,
            )
        )
    return tuple(accelerators)


class _ProbeFailedError(Exception):
    """Raised so that lru_cache does not remember a failed probe."""


@lru_cache(maxsize=1)
def _macos_accelerators() -> tuple[Accelerator, ...]:
    output = _run(["system_profiler", "SPDisplaysDataType", "-json"])
    if output is None:
        raise _ProbeFailedError
    return parse_macos_displays(output)


def _accelerators() -> tuple[Accelerator, ...]:
    # GPU enumeration is implemented for macOS only. On Linux the `runtimes`
    # list reports whether ROCm/CUDA tooling is present; per-device parsing is
    # deferred until it can be verified on real AMD hardware.
    if platform.system() != "Darwin":
        return ()
    try:
        return _macos_accelerators()
    except _ProbeFailedError:
        return ()


def _disk_usage() -> tuple[int, int]:
    """(total, free) bytes of the volume holding the working directory."""
    try:
        usage = psutil.disk_usage(str(Path.cwd()))
    except OSError:
        # The working directory can disappear under a long-running process.
        usage = psutil.disk_usage(str(Path.home()))
    return usage.total, usage.free


def _torch_runtime() -> RuntimeSupport:
    try:
        version = metadata.version("torch")
    except metadata.PackageNotFoundError:
        return RuntimeSupport(
            name="torch",
            available=False,
            detail="PyTorch is not installed. Install the 'ml' extra to enable training.",
        )
    return RuntimeSupport(
        name="torch",
        available=True,
        version=version,
        detail="PyTorch is installed. Device backends are not probed at startup.",
    )


def _runtimes() -> tuple[RuntimeSupport, ...]:
    metal = _is_apple_silicon()
    rocm_tool = shutil.which("amd-smi") or shutil.which("rocm-smi")
    rocm_dir = Path("/opt/rocm")
    rocm = bool(rocm_tool) or rocm_dir.exists()
    nvidia_tool = shutil.which("nvidia-smi")
    return (
        RuntimeSupport(
            name="metal",
            available=metal,
            detail="Apple Silicon GPU via Metal."
            if metal
            else "Metal requires an Apple Silicon Mac.",
        ),
        RuntimeSupport(
            name="rocm",
            available=rocm,
            detail=f"ROCm tooling found at {rocm_tool or rocm_dir}."
            if rocm
            else "No ROCm tooling found on this machine. ROCm workloads run on remote AMD GPUs.",
        ),
        RuntimeSupport(
            name="cuda",
            available=nvidia_tool is not None,
            detail=f"nvidia-smi found at {nvidia_tool}."
            if nvidia_tool
            else "nvidia-smi not found on this machine.",
        ),
        _torch_runtime(),
    )


def detect_local_hardware() -> HardwareProfile:
    """Return a snapshot of the machine this process is running on."""
    memory = psutil.virtual_memory()
    disk_total, disk_free = _disk_usage()
    return HardwareProfile(
        hostname=socket.gethostname(),
        os=platform.system(),
        os_version=platform.mac_ver()[0] or platform.release(),
        architecture=platform.machine(),
        python_version=platform.python_version(),
        cpu_model=_cpu_model(),
        cpu_physical_cores=psutil.cpu_count(logical=False),
        cpu_logical_cores=psutil.cpu_count(logical=True),
        memory_total_bytes=memory.total,
        memory_available_bytes=memory.available,
        disk_total_bytes=disk_total,
        disk_free_bytes=disk_free,
        accelerators=_accelerators(),
        runtimes=_runtimes(),
    )
