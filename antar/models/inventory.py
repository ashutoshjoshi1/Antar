"""Model inventory: the union of what every reachable backend reports."""

import asyncio
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from antar.backends.base import Availability, BackendStatus, RuntimeBackend
from antar.core.errors import BackendRequestError, BackendUnavailableError
from antar.models.spec import ModelSpec


class InventorySource(BaseModel):
    model_config = ConfigDict(frozen=True)

    backend: str
    display_name: str
    availability: Availability
    model_count: int
    detail: str


class ModelInventory(BaseModel):
    model_config = ConfigDict(frozen=True)

    models: tuple[ModelSpec, ...]
    sources: tuple[InventorySource, ...]


async def _collect_one(backend: RuntimeBackend) -> tuple[BackendStatus, tuple[ModelSpec, ...]]:
    status = await backend.status()
    if status.availability is not Availability.AVAILABLE:
        return status, ()
    try:
        return status, await backend.list_models()
    except (BackendUnavailableError, BackendRequestError) as exc:
        # The backend answered the health check but failed to list models.
        unavailable = status.model_copy(
            update={"availability": Availability.UNAVAILABLE, "detail": str(exc)}
        )
        return unavailable, ()


async def collect_inventory(backends: Sequence[RuntimeBackend]) -> ModelInventory:
    results = await asyncio.gather(*(_collect_one(backend) for backend in backends))
    return ModelInventory(
        models=tuple(model for _, models in results for model in models),
        sources=tuple(
            InventorySource(
                backend=status.name,
                display_name=status.display_name,
                availability=status.availability,
                model_count=len(models),
                detail=status.detail,
            )
            for status, models in results
        ),
    )
