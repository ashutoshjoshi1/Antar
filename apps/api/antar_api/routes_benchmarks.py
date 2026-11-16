"""Benchmark routes: configure, run, watch, cancel, review, export."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from antar.benchmarking.config import BenchmarkConfig
from antar.benchmarking.report import BenchmarkReport
from antar.benchmarking.store import BenchmarkStore, to_csv
from antar.benchmarking.workloads import WORKLOADS
from antar_api.routes_inference import BenchmarksDep
from antar_api.schemas import (
    BenchmarkHistoryResponse,
    BenchmarkStateResponse,
    ManualEvaluationBody,
    WorkloadsResponse,
)


def get_store(request: Request) -> BenchmarkStore:
    store: BenchmarkStore = request.app.state.benchmark_store
    return store


StoreDep = Annotated[BenchmarkStore, Depends(get_store)]

router = APIRouter(prefix="/api/v1/benchmarks", tags=["benchmarks"])


@router.get("/workloads")
async def workloads() -> WorkloadsResponse:
    return WorkloadsResponse(workloads=WORKLOADS)


@router.get("")
async def history(store: StoreDep) -> BenchmarkHistoryResponse:
    return BenchmarkHistoryResponse(benchmarks=await run_in_threadpool(store.list))


@router.post("", status_code=202)
async def start(config: BenchmarkConfig, manager: BenchmarksDep) -> BenchmarkStateResponse:
    """Start a benchmark in the background. Only one runs at a time."""
    return BenchmarkStateResponse(active=await manager.start(config))


@router.get("/active")
async def active(manager: BenchmarksDep) -> BenchmarkStateResponse:
    """Progress of the running benchmark, or the last one started by this process."""
    return BenchmarkStateResponse(active=manager.progress)


@router.post("/active/cancel")
async def cancel(manager: BenchmarksDep) -> BenchmarkStateResponse:
    """Stop the running benchmark. Requests already completed are saved."""
    manager.cancel()
    return BenchmarkStateResponse(active=manager.progress)


@router.get("/{report_id}")
async def report(report_id: str, store: StoreDep) -> BenchmarkReport:
    return await run_in_threadpool(store.get, report_id)


@router.get("/{report_id}/export")
async def export(
    report_id: str,
    store: StoreDep,
    export_format: Annotated[Literal["json", "csv"], Query(alias="format")] = "json",
) -> Response:
    result = await run_in_threadpool(store.get, report_id)
    if export_format == "csv":
        content, media_type = to_csv(result), "text/csv"
    else:
        content, media_type = result.model_dump_json(indent=2), "application/json"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{report_id}.{export_format}"'},
    )


@router.patch("/{report_id}/runs/{run_index}")
async def evaluate_run(
    report_id: str, run_index: int, body: ManualEvaluationBody, store: StoreDep
) -> BenchmarkReport:
    """Record a person's judgement of one response. Antar computes no score itself."""
    return await run_in_threadpool(
        lambda: store.set_manual_evaluation(
            report_id, run_index, score=body.score, notes=body.notes
        )
    )
