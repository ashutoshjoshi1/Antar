"""Comparison Lab routes: configure, run, watch, cancel, read, export."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from antar.comparison.export import to_csv, to_markdown
from antar.comparison.manager import ComparisonManager
from antar.comparison.report import ComparisonReport
from antar.comparison.store import ComparisonStore
from antar_api.schemas import (
    ComparisonBody,
    ComparisonHistoryResponse,
    ComparisonStateResponse,
)


def get_manager(request: Request) -> ComparisonManager:
    manager: ComparisonManager = request.app.state.comparisons
    return manager


def get_store(request: Request) -> ComparisonStore:
    store: ComparisonStore = request.app.state.comparison_store
    return store


ManagerDep = Annotated[ComparisonManager, Depends(get_manager)]
StoreDep = Annotated[ComparisonStore, Depends(get_store)]

router = APIRouter(prefix="/api/v1/comparisons", tags=["comparisons"])

_MEDIA = {"json": "application/json", "csv": "text/csv", "md": "text/markdown"}


@router.get("")
async def history(store: StoreDep) -> ComparisonHistoryResponse:
    return ComparisonHistoryResponse(comparisons=await run_in_threadpool(store.list))


@router.post("", status_code=202)
async def start(body: ComparisonBody, manager: ManagerDep) -> ComparisonStateResponse:
    """Start a comparison in the background. Uses paid cloud time, so it needs confirmation."""
    return ComparisonStateResponse(active=await manager.start(body.config))


@router.get("/active")
async def active(manager: ManagerDep) -> ComparisonStateResponse:
    """Progress of the running comparison, or the last one started by this process."""
    return ComparisonStateResponse(active=manager.progress)


@router.post("/active/cancel")
async def cancel(manager: ManagerDep) -> ComparisonStateResponse:
    """Stop the running comparison. The request in flight is aborted; finished ones are saved."""
    manager.cancel()
    return ComparisonStateResponse(active=manager.progress)


@router.get("/{report_id}")
async def report(report_id: str, store: StoreDep) -> ComparisonReport:
    return await run_in_threadpool(store.get, report_id)


@router.get("/{report_id}/export")
async def export(
    report_id: str,
    store: StoreDep,
    export_format: Annotated[Literal["json", "csv", "md"], Query(alias="format")] = "json",
) -> Response:
    result = await run_in_threadpool(store.get, report_id)
    if export_format == "csv":
        content = to_csv(result)
    elif export_format == "md":
        content = to_markdown(result)
    else:
        content = result.model_dump_json(indent=2)
    return Response(
        content=content,
        media_type=_MEDIA[export_format],
        headers={"Content-Disposition": f'attachment; filename="{report_id}.{export_format}"'},
    )
