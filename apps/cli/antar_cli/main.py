"""Antar command-line interface."""

import asyncio

import typer

from antar.backends.mock.backend import MockBackend
from antar.backends.registry import build_backends
from antar.config.settings import get_settings
from antar.core.errors import AntarError
from antar.hardware.detect import detect_local_hardware
from antar.inference.types import ChatMessage, ChatRequest, GenerationSettings
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


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address."),
    port: int = typer.Option(8080, help="Port."),
    reload: bool = typer.Option(False, help="Reload on code changes."),
) -> None:
    """Start the Antar API server."""
    import uvicorn

    uvicorn.run("antar_api.main:app", host=host, port=port, reload=reload)
