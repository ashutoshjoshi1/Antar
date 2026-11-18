"""AMD cloud routes: connection, hardware, GPU readings, sizing, cost, and Lemonade registration.

Nothing here starts, stops, or resizes a machine, and no request can name a
URL or a command: the endpoint, the SSH host, and every remote command come
from the server's own configuration and code.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from antar.backends.amd_cloud.backend import AmdCloudBackend
from antar.backends.amd_cloud.config import is_loopback
from antar.backends.amd_cloud.cost import (
    CloudSession,
    CloudSessionStore,
    CostEstimate,
    estimate_cost,
)
from antar.backends.amd_cloud.feasibility import FeasibilityEstimate, estimate_feasibility
from antar.backends.amd_cloud.preflight import PreflightReport, run_preflight
from antar.backends.amd_cloud.ssh import RemoteRunner
from antar.backends.base import Availability
from antar.backends.lemonade.backend import LemonadeBackend
from antar.core.errors import (
    AntarError,
    BackendUnavailableError,
    CapabilityNotSupportedError,
    ModelNotFoundError,
)
from antar.models.catalog import KNOWN_MODELS, find_known_model
from antar.models.spec import ModelSpec
from antar_api.routes import BackendsDep, SettingsDep
from antar_api.schemas import (
    LEMONADE_PROVIDER_NAME,
    CloudCatalogResponse,
    CloudStatusResponse,
    ConfirmBody,
    FeasibilityBody,
    GpuTelemetryResponse,
    LemonadeProviderResponse,
)

router = APIRouter(prefix="/api/v1/cloud", tags=["cloud"])


def get_cloud_backend(backends: BackendsDep) -> AmdCloudBackend:
    backend = next((item for item in backends if isinstance(item, AmdCloudBackend)), None)
    if backend is None:
        raise CapabilityNotSupportedError("The AMD cloud backend is not registered.")
    return backend


def get_lemonade(backends: BackendsDep) -> LemonadeBackend:
    backend = next((item for item in backends if isinstance(item, LemonadeBackend)), None)
    if backend is None:
        raise CapabilityNotSupportedError("The Lemonade backend is not registered.")
    return backend


def get_session_store(request: Request) -> CloudSessionStore:
    store: CloudSessionStore = request.app.state.cloud_sessions
    return store


def get_remote_runner(request: Request) -> RemoteRunner | None:
    runner: RemoteRunner | None = request.app.state.remote_runner
    return runner


CloudDep = Annotated[AmdCloudBackend, Depends(get_cloud_backend)]
LemonadeDep = Annotated[LemonadeBackend, Depends(get_lemonade)]
SessionsDep = Annotated[CloudSessionStore, Depends(get_session_store)]
RunnerDep = Annotated[RemoteRunner | None, Depends(get_remote_runner)]

_NO_SSH = "No SSH host is configured (amd_cloud in the configuration)."


@router.get("/status")
async def status(settings: SettingsDep, cloud: CloudDep) -> CloudStatusResponse:
    """Whether the endpoint is configured and reachable, and what it is serving."""
    endpoint, profile = settings.cloud, settings.amd_cloud
    backend_status = await cloud.status()
    round_trip_ms: float | None = None
    models: tuple[ModelSpec, ...] = ()
    if backend_status.availability is Availability.AVAILABLE:
        try:
            round_trip_ms = await cloud.ping_ms()
            models = await cloud.list_models()
        except AntarError:
            round_trip_ms = None
    return CloudStatusResponse(
        endpoint_configured=endpoint is not None,
        base_url=str(endpoint.base_url) if endpoint else None,
        loopback=is_loopback(endpoint.base_url.host or "") if endpoint else None,
        api_key_configured=bool(endpoint and endpoint.api_key),
        ssh_configured=profile is not None,
        ssh_host=profile.ssh_host if profile else None,
        vllm_image=endpoint.vllm_image if endpoint else None,
        status=backend_status,
        round_trip_ms=round_trip_ms,
        models=models,
    )


@router.get("/gpus")
async def gpus(settings: SettingsDep, cloud: CloudDep) -> GpuTelemetryResponse:
    """Device-level GPU readings from ``amd-smi`` on the host. Cached between samples."""
    profile = settings.amd_cloud
    return GpuTelemetryResponse(
        ssh_configured=profile is not None,
        interval_seconds=profile.gpu_poll_interval_seconds if profile else None,
        sample=await cloud.gpu_sample(),
        reason=None if profile else _NO_SSH,
    )


@router.post("/preflight")
async def preflight(runner: RunnerDep) -> PreflightReport:
    """Run the read-only environment check on the AMD host over SSH."""
    if runner is None:
        raise BackendUnavailableError(_NO_SSH)
    return await run_preflight(runner)


@router.get("/catalog")
async def catalog() -> CloudCatalogResponse:
    """Models whose published facts Antar has verified, for sizing a deployment."""
    return CloudCatalogResponse(models=KNOWN_MODELS)


@router.post("/feasibility")
async def feasibility(body: FeasibilityBody) -> FeasibilityEstimate:
    """An approximate memory budget for serving a catalog model. Arithmetic, not a measurement."""
    model = find_known_model(body.model)
    if model is None:
        raise ModelNotFoundError(
            f"'{body.model}' is not in Antar's catalog, so its size and shape are not known."
        )
    return estimate_feasibility(model, body)


@router.get("/cost")
async def cost(settings: SettingsDep, sessions: SessionsDep) -> CostEstimate:
    session = await run_in_threadpool(sessions.load)
    return estimate_cost(session, settings.cloud_cost)


@router.put("/cost")
async def set_cost(
    body: CloudSession, settings: SettingsDep, sessions: SessionsDep
) -> CostEstimate:
    """Record the operator's price, credit, and instance times. Antar verifies none of them."""
    session = await run_in_threadpool(sessions.save, body)
    return estimate_cost(session, settings.cloud_cost)


async def _provider_view(lemonade: LemonadeBackend) -> LemonadeProviderResponse:
    try:
        providers = await lemonade.cloud_providers()
    except AntarError as exc:
        return LemonadeProviderResponse(
            name=LEMONADE_PROVIDER_NAME, lemonade_reachable=False, supported=None, detail=str(exc)
        )
    if providers is None:
        return LemonadeProviderResponse(
            name=LEMONADE_PROVIDER_NAME,
            lemonade_reachable=True,
            supported=False,
            detail="This Lemonade version does not report cloud provider support.",
        )
    return LemonadeProviderResponse(
        name=LEMONADE_PROVIDER_NAME,
        lemonade_reachable=True,
        supported=True,
        provider=next((item for item in providers if item.name == LEMONADE_PROVIDER_NAME), None),
    )


@router.get("/lemonade-provider")
async def lemonade_provider(lemonade: LemonadeDep) -> LemonadeProviderResponse:
    """Whether the cloud endpoint is registered with Lemonade's own cloud routing."""
    return await _provider_view(lemonade)


@router.post("/lemonade-provider")
async def register_lemonade_provider(
    _: ConfirmBody, settings: SettingsDep, lemonade: LemonadeDep
) -> LemonadeProviderResponse:
    """Register the configured endpoint as a Lemonade cloud provider. Requires ``confirm``.

    This changes Lemonade's configuration and hands it the endpoint's API key,
    which Lemonade holds in memory. The URL is the one in Antar's settings.
    """
    endpoint = settings.cloud
    if endpoint is None:
        raise BackendUnavailableError("No cloud endpoint is configured to register.")
    lemonade_url = settings.lemonade.base_url
    if not is_loopback(lemonade_url.host or "") and (
        lemonade_url.scheme != "https" or is_loopback(endpoint.base_url.host or "")
    ):
        # A remote Lemonade would receive the key over the network, and a loopback
        # endpoint address means a different machine there.
        raise CapabilityNotSupportedError(
            "Registration needs Lemonade on this machine. Lemonade is configured at "
            f"{lemonade_url.host}, so the endpoint key will not be sent to it."
        )
    await lemonade.register_cloud_provider(
        LEMONADE_PROVIDER_NAME,
        str(endpoint.base_url).rstrip("/"),
        endpoint.api_key.get_secret_value() if endpoint.api_key else None,
    )
    return await _provider_view(lemonade)


@router.delete("/lemonade-provider")
async def remove_lemonade_provider(lemonade: LemonadeDep) -> LemonadeProviderResponse:
    await lemonade.remove_cloud_provider(LEMONADE_PROVIDER_NAME)
    return await _provider_view(lemonade)
