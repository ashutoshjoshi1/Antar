"""Runs one local-versus-cloud comparison at a time in the background.

A comparison is two ordinary benchmark runs — the local side, then the cloud
side — with the same workloads and settings, plus what only makes sense for
the pair: GPU readings taken while the cloud side runs, the round-trip cost of
the path to it, and the cloud time the run used.
"""

import asyncio
import logging
import secrets
import statistics
import time
from collections.abc import Callable, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from antar import __version__
from antar.backends.amd_cloud.backend import AmdCloudBackend
from antar.backends.amd_cloud.config import CloudCostSettings
from antar.backends.amd_cloud.cost import CloudSession, duration_cost
from antar.backends.base import BackendKind, RuntimeBackend
from antar.benchmarking.manager import BenchmarkManager, JobSlot, current_git_commit
from antar.benchmarking.report import BenchmarkReport
from antar.benchmarking.runner import BenchmarkRunner, total_requests
from antar.comparison.report import (
    CloudUsage,
    ComparisonConfig,
    ComparisonReport,
    ComparisonStatus,
    Side,
    TransportMeasurement,
    build_rows,
    summarize_gpu,
)
from antar.comparison.store import ComparisonStore
from antar.core.errors import AntarError, CapabilityNotSupportedError
from antar.core.types import utc_now
from antar.hardware.gpu import GpuSample
from antar.models.spec import ExecutionLocation, ModelSpec

logger = logging.getLogger(__name__)

_PING_COUNT = 5


class ComparisonProgress(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    status: str
    side: Side | None = None
    completed_requests: int
    total_requests: int
    current: str | None = None
    started_at: datetime
    budget_seconds: float
    failure: str | None = None


def _check_sides(local: ModelSpec, cloud: ModelSpec) -> None:
    if local.location is ExecutionLocation.CLOUD:
        raise CapabilityNotSupportedError(
            f"'{local.id}' runs in the cloud. Choose a model that runs on this machine for the "
            "local side."
        )
    if cloud.location is ExecutionLocation.LOCAL:
        raise CapabilityNotSupportedError(
            f"'{cloud.id}' runs on this machine. Choose a cloud model for the cloud side."
        )


class ComparisonManager:
    def __init__(
        self,
        backends: Sequence[RuntimeBackend],
        benchmarks: BenchmarkManager,
        store: ComparisonStore,
        slot: JobSlot,
        *,
        cost: CloudCostSettings,
        session: Callable[[], CloudSession],
        vllm_image: str | None = None,
        gpu_interval_seconds: float = 10.0,
    ) -> None:
        self._backends = tuple(backends)
        self._benchmarks = benchmarks
        self._store = store
        self._slot = slot
        self._cost = cost
        self._session = session
        self._vllm_image = vllm_image
        self._gpu_interval = gpu_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._runner: BenchmarkRunner | None = None
        self._progress: ComparisonProgress | None = None
        self._cancelled: str | None = None

    @property
    def progress(self) -> ComparisonProgress | None:
        """The running comparison, or the most recent one from this process."""
        return self._progress

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _update(self, report_id: str, **changes: object) -> None:
        if self._progress is not None and self._progress.id == report_id:
            self._progress = self._progress.model_copy(update=changes)

    async def start(self, config: ComparisonConfig) -> ComparisonProgress:
        self._slot.acquire("comparison")
        try:
            local = await self._benchmarks.prepare(config.benchmark_config("local"))
            cloud = await self._benchmarks.prepare(config.benchmark_config("cloud"))
            _check_sides(local[1], cloud[1])
        except BaseException:
            self._slot.release()
            raise

        report_id = f"cmp-{utc_now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        budget = (config.time_budget_minutes or self._cost.max_experiment_minutes) * 60
        self._cancelled = None
        self._progress = ComparisonProgress(
            id=report_id,
            name=config.name,
            status="running",
            completed_requests=0,
            total_requests=2 * total_requests(config.benchmark_config("local")),
            started_at=utc_now(),
            budget_seconds=budget,
        )
        # A mock on the cloud side touches no cloud: no GPUs, no path, and no paid time to report.
        remote = cloud[1].location is ExecutionLocation.CLOUD
        self._task = asyncio.create_task(self._execute(report_id, config, budget, remote=remote))
        return self._progress

    def cancel(self, reason: str = "Cancelled by the user.") -> bool:
        """Stop the comparison. Whatever finished is still saved."""
        if not self.is_running:
            return False
        self._cancelled = self._cancelled or reason
        if self._runner is not None:
            self._runner.cancel()
        return True

    async def wait(self) -> None:
        if self._task is not None:
            await self._task

    async def _run_side(
        self, report_id: str, config: ComparisonConfig, side: Side, offset: int
    ) -> BenchmarkReport:
        side_config = config.benchmark_config(side)
        # Captured again right before the side runs, so the snapshot is current.
        backend, _, environment = await self._benchmarks.prepare(side_config)

        def on_progress(completed: int, current: str | None) -> None:
            self._update(
                report_id, side=side, completed_requests=offset + completed, current=current
            )

        runner = BenchmarkRunner(backend, side_config, environment, on_progress=on_progress)
        self._runner = runner
        if self._cancelled:
            runner.cancel()
        try:
            return await runner.run(f"{report_id}-{side}")
        finally:
            self._runner = None

    def _gpu_source(self, cloud_backend: str) -> RuntimeBackend | None:
        """The backend that can read the cloud GPUs: the cloud side itself, or the AMD host."""
        named = [backend for backend in self._backends if backend.name == cloud_backend]
        cloud = [backend for backend in self._backends if backend.kind is BackendKind.CLOUD]
        return next(iter([*named, *cloud]), None)

    async def _sample_gpus(self, source: RuntimeBackend, samples: list[GpuSample]) -> None:
        while True:
            sample = await source.gpu_sample()
            if sample is None:
                return
            # The monitor returns its cached sample inside the interval; keep each one once.
            if not samples or samples[-1].collected_at != sample.collected_at:
                samples.append(sample)
            await asyncio.sleep(self._gpu_interval)

    async def _transport(self) -> TransportMeasurement | None:
        backend = next((item for item in self._backends if isinstance(item, AmdCloudBackend)), None)
        if backend is None:
            return None
        samples: list[float] = []
        try:
            for _ in range(_PING_COUNT):
                samples.append(await backend.ping_ms())
        except AntarError:
            if not samples:
                return None
        return TransportMeasurement(
            samples_ms=tuple(samples),
            median_ms=statistics.median(samples),
            note=(
                "Round trips of GET /health on the cloud endpoint, measured by the Antar API. "
                "No inference is involved, so this approximates the cost of the path alone."
            ),
        )

    async def _lemonade_version(self) -> str | None:
        for backend in self._backends:
            if backend.name == "lemonade":
                return (await backend.status()).version
        return None

    async def _execute(
        self, report_id: str, config: ComparisonConfig, budget: float, *, remote: bool
    ) -> None:
        loop = asyncio.get_running_loop()
        watchdog = loop.call_later(
            budget,
            self.cancel,
            f"Stopped at the {budget / 60:g}-minute time budget for experiments.",
        )
        started_at = utc_now()
        local: BenchmarkReport | None = None
        cloud: BenchmarkReport | None = None
        samples: list[GpuSample] = []
        cloud_seconds: float | None = None
        failure: str | None = None
        status: ComparisonStatus = "completed"
        source = self._gpu_source(config.cloud.backend) if remote else None
        try:
            local = await self._run_side(report_id, config, "local", 0)
            if local.status == "failed":
                # Nothing to compare against, so do not spend cloud time on the other half.
                raise AntarError(f"The local side failed: {local.failure}")
            sampler = asyncio.create_task(self._sample_gpus(source, samples)) if source else None
            cloud_started = time.perf_counter()
            try:
                cloud = await self._run_side(
                    report_id, config, "cloud", total_requests(config.benchmark_config("local"))
                )
            finally:
                cloud_seconds = time.perf_counter() - cloud_started if remote else None
                if sampler is not None:
                    sampler.cancel()
                    await asyncio.gather(sampler, return_exceptions=True)
            if self._cancelled:
                status, failure = "cancelled", self._cancelled
            elif cloud.status == "failed":
                status, failure = "failed", f"The cloud side failed: {cloud.failure}"
        except AntarError as exc:
            status, failure = "failed", str(exc)
        except Exception:
            logger.exception("Comparison %s crashed", report_id)
            status, failure = "failed", "The comparison stopped unexpectedly. See the API log."
        finally:
            watchdog.cancel()

        try:
            price = self._session().hourly_price_usd
            report = ComparisonReport(
                id=report_id,
                status=status,
                simulated=any(side is not None and side.simulated for side in (local, cloud)),
                antar_version=__version__,
                git_commit=await asyncio.to_thread(current_git_commit),
                config=config,
                local=local,
                cloud=cloud,
                rows=build_rows(local, cloud, config.workloads),
                transport=await self._transport() if remote else None,
                gpu=summarize_gpu(samples, self._gpu_interval),
                usage=CloudUsage(
                    cloud_seconds=cloud_seconds,
                    hourly_price_usd=price,
                    estimated_cost_usd=duration_cost(cloud_seconds, price)
                    if cloud_seconds is not None
                    else None,
                ),
                vllm_image=self._vllm_image,
                lemonade_version=await self._lemonade_version(),
                failure=failure,
                started_at=started_at,
                finished_at=utc_now(),
            )
            await asyncio.to_thread(self._store.save, report)
        except Exception:
            logger.exception("Comparison %s could not be saved", report_id)
            status, failure = "failed", "The comparison could not be saved. See the API log."
        finally:
            self._slot.release()
        self._update(report_id, status=status, failure=failure, current=None, side=None)
