"""The benchmark runner: sequential, real requests against one backend."""

import asyncio
import json
import logging
import time
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from antar import __version__
from antar.backends.base import RuntimeBackend
from antar.benchmarking.config import BenchmarkConfig
from antar.benchmarking.report import (
    BenchmarkReport,
    ColdStart,
    ModelSnapshot,
    Phase,
    ReportStatus,
    RunRecord,
    build_aggregates,
)
from antar.benchmarking.workloads import BenchmarkPrompt, Workload, get_workload, load_image
from antar.core.errors import AntarError
from antar.core.types import utc_now
from antar.hardware.profile import HardwareProfile
from antar.hardware.telemetry import Unavailable
from antar.inference.types import (
    ChatDone,
    ChatMessage,
    ChatRequest,
    ChatResult,
    GenerationSettings,
)

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class BenchmarkEnvironment(BaseModel):
    """Facts about where the benchmark runs, captured once before it starts."""

    model_config = ConfigDict(frozen=True)

    hardware: HardwareProfile
    model: ModelSnapshot
    backend_version: str | None = None
    git_commit: str | None = None
    missing_telemetry: tuple[Unavailable, ...] = ()
    simulated: bool = False


class BenchmarkProgress(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    model: str
    status: str
    completed_requests: int
    total_requests: int
    current: str | None = None
    started_at: datetime
    failure: str | None = None


ProgressCallback = Callable[[int, str | None], None]


def total_requests(config: BenchmarkConfig) -> int:
    per_workload = sum(
        config.warmup_runs + config.measured_runs * len(get_workload(workload_id).prompts)
        for workload_id in config.workloads
    )
    return per_workload + (1 if config.load_policy == "reload" else 0)


def strip_code_fence(text: str) -> str:
    """Models often wrap JSON in a Markdown fence; that is still valid JSON output."""
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped[3:-3].strip()
        first_line, _, rest = stripped.partition("\n")
        if rest and first_line.strip().isalpha():
            stripped = rest
    return stripped


def is_valid_json(text: str) -> bool:
    try:
        json.loads(strip_code_fence(text))
    except ValueError:
        return False
    return True


class _Cancelled(Exception):
    pass


class BenchmarkRunner:
    def __init__(
        self,
        backend: RuntimeBackend,
        config: BenchmarkConfig,
        environment: BenchmarkEnvironment,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._backend = backend
        self._config = config
        self._environment = environment
        self._on_progress = on_progress
        self._cancel = asyncio.Event()
        self._runs: list[RunRecord] = []
        self._completed = 0

    def cancel(self) -> None:
        self._cancel.set()

    def _report_progress(self, current: str | None) -> None:
        if self._on_progress:
            self._on_progress(self._completed, current)

    def _request(self, prompt: BenchmarkPrompt) -> ChatRequest:
        config = self._config
        images = (load_image(prompt.image),) if prompt.image else ()
        return ChatRequest(
            model=config.model.id,
            messages=(ChatMessage(role="user", content=prompt.text, images=images),),
            settings=GenerationSettings(
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                seed=config.seed,
                enable_thinking=config.enable_thinking,
            ),
        )

    async def _consume(self, request: ChatRequest) -> ChatResult:
        async for event in self._backend.chat_stream(request):
            if isinstance(event, ChatDone):
                return event.result
        raise AntarError("The backend ended the stream without a final result.")

    async def _guarded(self, operation: Coroutine[object, object, _T]) -> _T:
        """Await a backend call, abandoning it immediately if the benchmark is cancelled."""
        task = asyncio.ensure_future(operation)
        waiter = asyncio.ensure_future(self._cancel.wait())
        try:
            await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
            if not task.done():
                raise _Cancelled
            return task.result()
        finally:
            # Cancelling the task closes its connection, which stops the backend working.
            for pending in (task, waiter):
                if not pending.done():
                    pending.cancel()
            await asyncio.gather(task, waiter, return_exceptions=True)

    async def _run_one(
        self, workload: Workload, prompt: BenchmarkPrompt, phase: Phase
    ) -> RunRecord:
        if self._cancel.is_set():
            raise _Cancelled
        self._report_progress(f"{workload.name}: {prompt.id} ({phase})")
        index = len(self._runs)
        try:
            result = await self._guarded(self._consume(self._request(prompt)))
        except AntarError as exc:
            record = RunRecord(
                index=index,
                workload=workload.id,
                prompt_id=prompt.id,
                phase=phase,
                ok=False,
                error=str(exc),
            )
        else:
            record = RunRecord(
                index=index,
                workload=workload.id,
                prompt_id=prompt.id,
                phase=phase,
                ok=True,
                metrics=result.metrics,
                response=result.content,
                finish_reason=result.finish_reason,
                json_valid=is_valid_json(result.content) if workload.check == "json" else None,
            )
        self._runs.append(record)
        self._completed += 1
        return record

    async def _cold_start(self, first: Workload) -> ColdStart:
        self._report_progress("Reloading the model")
        model = self._config.model.id
        await self._guarded(self._backend.unload_model(model))
        started = time.perf_counter()
        await self._guarded(self._backend.load_model(model))
        load_time_ms = (time.perf_counter() - started) * 1000
        record = await self._run_one(first, first.prompts[0], "cold")
        return ColdStart(load_time_ms=load_time_ms, first_request=record)

    async def run(self, report_id: str) -> BenchmarkReport:
        config = self._config
        workloads = tuple(get_workload(workload_id) for workload_id in config.workloads)
        started_at = utc_now()
        cold_start: ColdStart | None = None
        status: ReportStatus = "completed"
        failure: str | None = None

        try:
            if config.load_policy == "reload":
                cold_start = await self._cold_start(workloads[0])
            else:
                self._report_progress("Loading the model")
                await self._guarded(self._backend.load_model(config.model.id))
            for workload in workloads:
                for iteration in range(config.warmup_runs):
                    prompt = workload.prompts[iteration % len(workload.prompts)]
                    await self._run_one(workload, prompt, "warmup")
                for _ in range(config.measured_runs):
                    for prompt in workload.prompts:
                        await self._run_one(workload, prompt, "measured")
        except _Cancelled:
            status = "cancelled"
        except AntarError as exc:
            # Loading failed (for example, not enough memory): nothing could be measured.
            status, failure = "failed", str(exc)
        except Exception:
            # Keep whatever was measured rather than losing the whole run to a bug.
            logger.exception("Benchmark %s stopped unexpectedly", report_id)
            status, failure = "failed", "The benchmark stopped unexpectedly. See the API log."

        self._report_progress(None)
        runs = tuple(self._runs)
        return BenchmarkReport(
            id=report_id,
            status=status,
            simulated=self._environment.simulated,
            antar_version=__version__,
            git_commit=self._environment.git_commit,
            backend=config.backend,
            backend_version=self._environment.backend_version,
            model=self._environment.model,
            hardware=self._environment.hardware,
            config=config,
            workloads=workloads,
            cold_start=cold_start,
            runs=runs,
            aggregates=build_aggregates(runs, config.workloads),
            missing_telemetry=self._environment.missing_telemetry,
            failure=failure,
            started_at=started_at,
            finished_at=utc_now(),
        )
