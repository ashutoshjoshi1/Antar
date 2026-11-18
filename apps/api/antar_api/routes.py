"""HTTP routes. Handlers stay thin: they call into ``antar`` and shape the response."""

import asyncio
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from antar import __version__
from antar.backends.amd_cloud.config import is_loopback
from antar.backends.base import RuntimeBackend
from antar.config.settings import CONFIG_FILE_ENV, DEFAULT_CONFIG_FILE, Settings
from antar.core.types import utc_now
from antar.hardware.detect import detect_local_hardware
from antar.hardware.profile import HardwareProfile
from antar.modalities.catalog import MODALITY_CATALOG
from antar.models.inventory import ModelInventory, collect_inventory
from antar.optimization.job import TECHNIQUE_MATRIX
from antar.orchestration.experiment import ExperimentStore
from antar_api.schemas import (
    AmdCloudSettingsView,
    BackendCapabilities,
    BackendsResponse,
    CapabilitiesResponse,
    CloudCostView,
    CloudEndpointView,
    ExperimentsResponse,
    HealthResponse,
    InferenceLimitsView,
    LemonadeSettingsView,
    SettingsResponse,
    StorageSettingsView,
)


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_backends(request: Request) -> tuple[RuntimeBackend, ...]:
    backends: tuple[RuntimeBackend, ...] = request.app.state.backends
    return backends


SettingsDep = Annotated[Settings, Depends(get_settings)]
BackendsDep = Annotated[tuple[RuntimeBackend, ...], Depends(get_backends)]

health_router = APIRouter(tags=["health"])
router = APIRouter(prefix="/api/v1")


@health_router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, time=utc_now())


@router.get("/system", tags=["hardware"])
async def system() -> HardwareProfile:
    return await run_in_threadpool(detect_local_hardware)


@router.get("/backends", tags=["backends"])
async def backends(runtime_backends: BackendsDep) -> BackendsResponse:
    statuses = await asyncio.gather(*(backend.status() for backend in runtime_backends))
    return BackendsResponse(backends=tuple(statuses))


@router.get("/models", tags=["models"])
async def models(runtime_backends: BackendsDep) -> ModelInventory:
    return await collect_inventory(runtime_backends)


@router.get("/capabilities", tags=["backends"])
async def capabilities(runtime_backends: BackendsDep) -> CapabilitiesResponse:
    statuses = await asyncio.gather(*(backend.status() for backend in runtime_backends))
    return CapabilitiesResponse(
        modalities=MODALITY_CATALOG,
        techniques=TECHNIQUE_MATRIX,
        backends=tuple(
            BackendCapabilities(
                backend=backend.name,
                display_name=backend.display_name,
                kind=backend.kind,
                availability=status.availability,
                capabilities=backend.capabilities(),
            )
            for backend, status in zip(runtime_backends, statuses, strict=True)
        ),
    )


@router.get("/settings", tags=["settings"])
def settings_view(settings: SettingsDep) -> SettingsResponse:
    """Effective configuration, read-only, with secrets reduced to booleans."""
    config_file = os.environ.get(CONFIG_FILE_ENV, DEFAULT_CONFIG_FILE)
    profile = settings.amd_cloud
    endpoint = settings.cloud
    storage = settings.storage
    return SettingsResponse(
        config_file=config_file,
        config_file_found=Path(config_file).is_file(),
        mock_backend_enabled=settings.enable_mock_backend,
        lemonade=LemonadeSettingsView(
            base_url=str(settings.lemonade.base_url),
            api_key_configured=settings.lemonade.api_key is not None,
            timeout_seconds=settings.lemonade.timeout_seconds,
        ),
        amd_cloud=AmdCloudSettingsView(
            name=profile.name,
            ssh_host=profile.ssh_host,
            ssh_user=profile.ssh_user,
            ssh_port=profile.ssh_port,
            ssh_key_configured=profile.ssh_key_path is not None,
            remote_workdir=profile.remote_workdir,
            rocm_version=profile.rocm_version,
            gpus=profile.gpus,
        )
        if profile
        else None,
        cloud=CloudEndpointView(
            base_url=str(endpoint.base_url),
            loopback=is_loopback(endpoint.base_url.host or ""),
            api_key_configured=endpoint.api_key is not None,
            trusted_hosts=endpoint.trusted_hosts,
            declared_models=tuple(model.id for model in endpoint.models),
            vllm_image=endpoint.vllm_image,
            generation_timeout_seconds=endpoint.generation_timeout_seconds,
        )
        if endpoint
        else None,
        cloud_cost=CloudCostView(
            hourly_price_usd=settings.cloud_cost.hourly_price_usd,
            credit_balance_usd=settings.cloud_cost.credit_balance_usd,
            max_experiment_minutes=settings.cloud_cost.max_experiment_minutes,
        ),
        inference=InferenceLimitsView(
            max_image_bytes=settings.max_image_bytes,
            generation_timeout_seconds=settings.lemonade.generation_timeout_seconds,
        ),
        storage=StorageSettingsView(
            models_dir=str(storage.models_dir),
            artifacts_dir=str(storage.artifacts_dir),
            training_dir=str(storage.training_dir),
            benchmarks_dir=str(storage.benchmarks_dir),
            experiments_dir=str(storage.experiments_dir),
            comparisons_dir=str(storage.comparisons_dir),
        ),
    )


@router.get("/experiments", tags=["experiments"])
async def experiments(settings: SettingsDep) -> ExperimentsResponse:
    store = ExperimentStore(settings.storage.experiments_dir)
    return ExperimentsResponse(experiments=await run_in_threadpool(store.list))
