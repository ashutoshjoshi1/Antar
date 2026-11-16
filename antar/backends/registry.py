"""Backend construction.

To add an inference engine: implement ``RuntimeBackend`` in a new subpackage
and register it in ``build_backends``. Nothing else in the application needs to
change — the API, model inventory, and dashboard all iterate over this list.
"""

import httpx

from antar.backends.amd_cloud.backend import AmdCloudBackend
from antar.backends.base import RuntimeBackend
from antar.backends.lemonade.backend import LemonadeBackend
from antar.backends.lemonade.client import LemonadeClient
from antar.backends.mock.backend import MockBackend
from antar.config.settings import Settings


def build_backends(
    settings: Settings, *, lemonade_transport: httpx.AsyncBaseTransport | None = None
) -> tuple[RuntimeBackend, ...]:
    lemonade = settings.lemonade
    backends: list[RuntimeBackend] = [
        LemonadeBackend(
            LemonadeClient(
                str(lemonade.base_url),
                api_key=lemonade.api_key.get_secret_value() if lemonade.api_key else None,
                timeout_seconds=lemonade.timeout_seconds,
                transport=lemonade_transport,
            )
        ),
        AmdCloudBackend(settings.amd_cloud),
    ]
    if settings.enable_mock_backend:
        backends.append(MockBackend())
    return tuple(backends)
