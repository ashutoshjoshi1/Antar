"""HTTP client for the Lemonade local server.

Written against the Lemonade API reference on the ``main`` branch of
https://github.com/lemonade-sdk/lemonade (``docs/api/``), checked 2026-11-16
against release v2026.46.2:

* Documented base URL is ``http://localhost:13305/v1``. Older prefixes
  (``/api/v1`` etc.) are still served, but only ``/v1`` is documented.
* ``GET /v1/health`` — server status, version, loaded models.
* ``GET /v1/models`` — OpenAI-style list with Lemonade fields; ``show_all=true``
  also lists catalog models that are not downloaded.
* Optional auth: ``Authorization: Bearer <LEMONADE_API_KEY>``.

Only the fields Antar uses are modelled; unknown fields are ignored so that
additive upstream changes do not break discovery.
"""

import logging

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from antar.core.errors import BackendUnavailableError

logger = logging.getLogger(__name__)

DEFAULT_LEMONADE_BASE_URL = "http://localhost:13305/v1"


class LemonadeLoadedModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    model_name: str
    type: str | None = None
    device: str | None = None
    recipe: str | None = None


class LemonadeHealth(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    status: str
    version: str | None = None
    model_loaded: str | None = None
    all_models_loaded: tuple[LemonadeLoadedModel, ...] = ()


class LemonadeModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(min_length=1)
    checkpoint: str | None = None
    recipe: str | None = None
    size: float | None = Field(default=None, description="Size in GB; omitted when unknown.")
    downloaded: bool | None = None
    labels: tuple[str, ...] = ()


class LemonadeClient:
    def __init__(
        self,
        base_url: str = DEFAULT_LEMONADE_BASE_URL,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout_seconds
        self._transport = transport

    async def _get_json(self, path: str, params: dict[str, str] | None = None) -> object:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(
                headers=self._headers, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise BackendUnavailableError(
                f"Lemonade did not respond within {self._timeout:g}s at {url}."
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendUnavailableError(
                f"Could not connect to Lemonade at {url}. Is the server installed and running?"
            ) from exc

        if response.status_code == httpx.codes.UNAUTHORIZED:
            raise BackendUnavailableError(
                "Lemonade rejected the request (401). Set ANTAR_LEMONADE__API_KEY to the "
                "server's LEMONADE_API_KEY."
            )
        if response.is_error:
            raise BackendUnavailableError(
                f"Lemonade returned HTTP {response.status_code} for {url}."
            )
        try:
            return response.json()
        except ValueError as exc:
            raise BackendUnavailableError(
                f"{url} did not return JSON. Check that the URL points at a Lemonade server "
                "and includes the /v1 prefix."
            ) from exc

    async def health(self) -> LemonadeHealth:
        payload = await self._get_json("/health")
        try:
            return LemonadeHealth.model_validate(payload)
        except ValidationError as exc:
            raise BackendUnavailableError(
                "Unexpected response from Lemonade /health; the server may be an "
                "incompatible version."
            ) from exc

    async def list_models(self, *, show_all: bool = False) -> tuple[LemonadeModel, ...]:
        payload = await self._get_json("/models", {"show_all": "true"} if show_all else None)
        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise BackendUnavailableError(
                "Unexpected response from Lemonade /models; the server may be an "
                "incompatible version."
            )
        models: list[LemonadeModel] = []
        for entry in entries:
            try:
                models.append(LemonadeModel.model_validate(entry))
            except ValidationError:
                # Skip the entry rather than lose the whole inventory.
                logger.warning("Skipping malformed Lemonade model entry: %r", entry)
        return tuple(models)
