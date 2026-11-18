"""Antar command-line interface."""

import asyncio

import typer

from antar.backends.amd_cloud.feasibility import (
    GIB,
    FeasibilityRequest,
    estimate_feasibility,
)
from antar.backends.amd_cloud.preflight import run_preflight
from antar.backends.mock.backend import MockBackend
from antar.backends.registry import build_backends, build_cloud_backend, build_remote_runner
from antar.config.settings import get_settings
from antar.core.errors import AntarError
from antar.hardware.detect import detect_local_hardware
from antar.inference.types import ChatMessage, ChatRequest, GenerationSettings
from antar.models.catalog import KNOWN_MODELS, find_known_model
from antar.models.inventory import collect_inventory

app = typer.Typer(
    help="Antar — cloud-scale intelligence, local freedom.",
    no_args_is_help=True,
    add_completion=False,
)

_GIB = 1024**3


@app.command()
def system() -> None:
    """Show the detected local hardware profile as JSON."""
    typer.echo(detect_local_hardware().model_dump_json(indent=2))


@app.command()
def backends() -> None:
    """Check every configured inference backend."""

    async def _statuses() -> None:
        for backend in build_backends(get_settings()):
            status = await backend.status()
            typer.echo(f"{status.name:<10} {status.availability.value:<16} {status.detail}")

    asyncio.run(_statuses())


@app.command()
def models() -> None:
    """List models reported by reachable backends."""
    inventory = asyncio.run(collect_inventory(build_backends(get_settings())))
    for model in inventory.models:
        size = f"{model.size_bytes / _GIB:.1f} GiB" if model.size_bytes is not None else "-"
        modalities = ",".join(modality.value for modality in model.modalities) or "unclassified"
        typer.echo(f"{model.backend:<10} {model.id:<44} {modalities:<20} {size}")
    for source in inventory.sources:
        if source.model_count == 0:
            typer.echo(
                f"# {source.backend}: {source.availability.value} — {source.detail}", err=True
            )


@app.command("mock-generate")
def mock_generate(
    prompt: str = typer.Argument(..., help="Prompt text."),
    model: str = typer.Option("mock/echo-small", help="Mock model id."),
    seed: int = typer.Option(0, help="Seed; identical inputs give identical output."),
) -> None:
    """Exercise the mock backend. Output is simulated, not real inference."""
    try:
        request = ChatRequest(
            model=model,
            messages=(ChatMessage(role="user", content=prompt),),
            settings=GenerationSettings(seed=seed),
        )
        result = asyncio.run(MockBackend().chat(request))
    except (AntarError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(result.model_dump_json(indent=2))


@app.command("cloud-status")
def cloud_status() -> None:
    """Check the configured AMD cloud endpoint and, if an SSH host is set, its GPUs."""

    async def _status() -> None:
        backend = build_cloud_backend(get_settings())
        status = await backend.status()
        typer.echo(f"{status.availability.value}: {status.detail}")
        if status.version:
            typer.echo(f"vLLM {status.version} at {status.endpoint}")
        sample = await backend.gpu_sample()
        if sample is None:
            typer.echo("GPU readings: unavailable (no SSH host configured).")
            return
        for gpu in sample.gpus:
            typer.echo(gpu.model_dump_json())
        for gap in sample.unavailable:
            typer.echo(f"# unavailable {gap.metric}: {gap.reason}", err=True)

    asyncio.run(_status())


@app.command("cloud-preflight")
def cloud_preflight() -> None:
    """Run the read-only environment check on the configured AMD host over SSH."""
    runner = build_remote_runner(get_settings())
    if runner is None:
        typer.echo("error: no SSH host configured (amd_cloud).", err=True)
        raise typer.Exit(code=1)
    try:
        report = asyncio.run(run_preflight(runner))
    except AntarError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for check in report.checks:
        typer.echo(f"{check.status.upper():<5} {check.id:<20} {check.detail}")
        if check.remediation and check.status != "pass":
            typer.echo(f"      fix: {check.remediation}")
    raise typer.Exit(code=0 if report.ok else 1)


@app.command("cloud-estimate")
def cloud_estimate(
    model: str = typer.Argument(..., help="A model id from Antar's catalog."),
    gpu_memory_gb: float = typer.Option(..., help="Memory of one GPU, in GiB."),
    gpus: int = typer.Option(1, help="Physical GPUs to use."),
    max_model_len: int | None = typer.Option(None, help="Context length to serve."),
    concurrency: int = typer.Option(1, help="Concurrent sequences to budget for."),
) -> None:
    """Approximate GPU memory needed to serve a catalog model. Arithmetic, not a measurement."""
    known = find_known_model(model)
    if known is None:
        catalog = ", ".join(item.id for item in KNOWN_MODELS)
        typer.echo(f"error: '{model}' is not in the catalog. Known: {catalog}.", err=True)
        raise typer.Exit(code=1)
    try:
        request = FeasibilityRequest(
            gpu_count=gpus,
            gpu_memory_bytes=round(gpu_memory_gb * GIB),
            max_model_len=max_model_len,
            concurrency=concurrency,
        )
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(estimate_feasibility(known, request).model_dump_json(indent=2))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address."),
    port: int = typer.Option(8080, help="Port."),
    reload: bool = typer.Option(False, help="Reload on code changes."),
) -> None:
    """Start the Antar API server."""
    import uvicorn

    uvicorn.run("antar_api.main:app", host=host, port=port, reload=reload)
