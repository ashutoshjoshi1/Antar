"""Runs one benchmark at a time in the background and tracks its progress."""

import asyncio
import logging
import secrets
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from antar.backends.base import Availability, BackendKind, RuntimeBackend
from antar.benchmarking.config import BenchmarkConfig
from antar.benchmarking.report import BenchmarkReport, ModelSnapshot
from antar.benchmarking.runner import (
    BenchmarkEnvironment,
    BenchmarkProgress,
    BenchmarkRunner,
    total_requests,
)
from antar.benchmarking.store import BenchmarkStore
from antar.benchmarking.workloads import get_workload
from antar.core.errors import (
    BackendUnavailableError,
    BenchmarkBusyError,
    CapabilityNotSupportedError,
    ModelNotDownloadedError,
    ModelNotFoundError,
)
from antar.core.types import Modality, utc_now
from antar.hardware.detect import detect_local_hardware
from antar.hardware.telemetry import Unavailable, collect_telemetry
from antar.inference.service import get_backend
from antar.models.spec import ModelSpec

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def current_git_commit() -> str | None:
    """Short commit hash of the Antar checkout, or None outside a git repository."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        completed = subprocess.run(
            [git, "-C", str(_REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


class BenchmarkManager:
    def __init__(self, backends: Sequence[RuntimeBackend], store: BenchmarkStore) -> None:
        self._backends = tuple(backends)
        self._store = store
        self._runner: BenchmarkRunner | None = None
        self._task: asyncio.Task[None] | None = None
        self._progress: BenchmarkProgress | None = None
        self._starting = False

    @property
    def progress(self) -> BenchmarkProgress | None:
        """The running benchmark, or the most recent one from this process."""
        return self._progress

    @property
    def is_running(self) -> bool:
        return self._starting or (self._task is not None and not self._task.done())

    async def _validate_model(self, backend: RuntimeBackend, config: BenchmarkConfig) -> ModelSpec:
        status = await backend.status()
        if status.availability is not Availability.AVAILABLE:
            raise BackendUnavailableError(status.detail)
        models = await backend.list_models()
        spec = next((model for model in models if model.id == config.model.id), None)
        if spec is None:
            raise ModelNotFoundError(f"{backend.display_name} has no model '{config.model.id}'.")
        if spec.downloaded is not True:
            raise ModelNotDownloadedError(
                f"'{spec.id}' is not downloaded. Download it from the Models page first."
            )
        needs_vision = any(
            get_workload(workload_id).modality is Modality.VISION
            for workload_id in config.workloads
        )
        if needs_vision and Modality.VISION not in spec.modalities:
            raise CapabilityNotSupportedError(
                f"'{spec.id}' does not accept images, so it cannot run a vision workload."
            )
        return spec

    async def start(self, config: BenchmarkConfig) -> BenchmarkProgress:
        if self.is_running:
            raise BenchmarkBusyError("A benchmark is already running. Wait for it or cancel it.")
        # Reserve the slot before the first await, so two requests cannot both get past
        # the check above while the first is still validating.
        self._starting = True
        try:
            return await self._start(config)
        finally:
            self._starting = False

    async def _start(self, config: BenchmarkConfig) -> BenchmarkProgress:
        backend = get_backend(self._backends, config.backend)
        spec = await self._validate_model(backend, config)
        status = await backend.status()
        hardware = await asyncio.to_thread(detect_local_hardware)
        telemetry = await asyncio.to_thread(collect_telemetry, await backend.model_processes())
        environment = BenchmarkEnvironment(
            hardware=hardware,
            model=ModelSnapshot(
                id=spec.id,
                checkpoint=spec.checkpoint,
                quantization=spec.quantization,
                runtime=spec.runtime,
                size_bytes=spec.size_bytes,
            ),
            backend_version=status.version,
            git_commit=await asyncio.to_thread(current_git_commit),
            missing_telemetry=(
                *telemetry.unavailable,
                Unavailable(
                    metric="peak_memory_per_request",
                    reason="The backend does not report memory use for individual requests.",
                ),
            ),
            simulated=backend.kind is BackendKind.MOCK,
        )

        report_id = f"bench-{utc_now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        progress = BenchmarkProgress(
            id=report_id,
            name=config.name,
            model=spec.id,
            status="running",
            completed_requests=0,
            total_requests=total_requests(config),
            started_at=utc_now(),
        )
        self._progress = progress

        def on_progress(completed: int, current: str | None) -> None:
            if self._progress is not None and self._progress.id == report_id:
                self._progress = self._progress.model_copy(
                    update={"completed_requests": completed, "current": current}
                )

        runner = BenchmarkRunner(backend, config, environment, on_progress=on_progress)
        self._runner = runner
        self._task = asyncio.create_task(self._execute(runner, report_id))
        return progress

    async def _execute(self, runner: BenchmarkRunner, report_id: str) -> None:
        try:
            report: BenchmarkReport = await runner.run(report_id)
            await asyncio.to_thread(self._store.save, report)
            update = {"status": report.status, "failure": report.failure, "current": None}
        except Exception:
            logger.exception("Benchmark %s crashed", report_id)
            update = {
                "status": "failed",
                "failure": "The benchmark stopped unexpectedly. See the Antar API log.",
                "current": None,
            }
        if self._progress is not None and self._progress.id == report_id:
            self._progress = self._progress.model_copy(update=update)

    def cancel(self) -> bool:
        """Ask the running benchmark to stop. Its partial results are still saved."""
        if self._task is None or self._task.done() or self._runner is None:
            return False
        self._runner.cancel()
        return True

    async def wait(self) -> None:
        if self._task is not None:
            await self._task
