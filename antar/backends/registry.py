"""Backend construction.

To add an inference engine: implement ``RuntimeBackend`` in a new subpackage
and register it in ``build_backends``. Nothing else in the application needs to
change — the API, model inventory, and dashboard all iterate over this list.
"""

import httpx

from antar.backends.amd_cloud.amd_smi import GpuMonitor
from antar.backends.amd_cloud.backend import AmdCloudBackend
from antar.backends.amd_cloud.ssh import RemoteRunner, SshRunner
from antar.backends.amd_cloud.vllm import VllmClient
from antar.backends.base import RuntimeBackend
from antar.backends.lemonade.backend import LemonadeBackend
from antar.backends.lemonade.client import LemonadeClient
from antar.backends.mock.backend import MockBackend
from antar.config.settings import Settings


def build_remote_runner(settings: Settings) -> RemoteRunner | None:
    """The SSH runner for the configured AMD host, or None when no host is configured."""
    return SshRunner(settings.amd_cloud) if settings.amd_cloud else None


def build_cloud_backend(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    runner: RemoteRunner | None = None,
) -> AmdCloudBackend:
    endpoint, profile = settings.cloud, settings.amd_cloud
    client = (
        VllmClient(
            str(endpoint.base_url),
            api_key=endpoint.api_key.get_secret_value() if endpoint.api_key else None,
            timeout_seconds=endpoint.timeout_seconds,
            generation_timeout_seconds=endpoint.generation_timeout_seconds,
            transport=transport,
        )
        if endpoint
        else None
    )
    remote = runner or build_remote_runner(settings)
    monitor = (
        GpuMonitor(remote, min_interval_seconds=profile.gpu_poll_interval_seconds)
        if remote and profile
        else None
    )
    return AmdCloudBackend(profile, endpoint=endpoint, client=client, monitor=monitor)


def build_backends(
    settings: Settings,
    *,
    lemonade_transport: httpx.AsyncBaseTransport | None = None,
    cloud_transport: httpx.AsyncBaseTransport | None = None,
    cloud_runner: RemoteRunner | None = None,
) -> tuple[RuntimeBackend, ...]:
    lemonade = settings.lemonade
    backends: list[RuntimeBackend] = [
        LemonadeBackend(
            LemonadeClient(
                str(lemonade.base_url),
                api_key=lemonade.api_key.get_secret_value() if lemonade.api_key else None,
                timeout_seconds=lemonade.timeout_seconds,
                generation_timeout_seconds=lemonade.generation_timeout_seconds,
                load_timeout_seconds=lemonade.load_timeout_seconds,
                transport=lemonade_transport,
            )
        ),
        build_cloud_backend(settings, transport=cloud_transport, runner=cloud_runner),
    ]
    if settings.enable_mock_backend:
        backends.append(MockBackend())
    return tuple(backends)
