"""AMD cloud configuration: the SSH host, the inference endpoint, and cost inputs.

Two independent pieces, both describing a machine that *you* have provisioned:

* ``AmdCloudProfile`` — how to reach the host over SSH. Used only for read-only
  checks (preflight, ``amd-smi``). Optional.
* ``CloudEndpointSettings`` — the vLLM OpenAI-compatible endpoint Antar sends
  inference to. Normally a loopback URL at the near end of an SSH tunnel.

Antar never starts, resizes, or stops the machine, and has no billing API:
``CloudCostSettings`` holds numbers the operator typed in.
"""

import ipaddress
import re
from pathlib import Path
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    field_validator,
    model_validator,
)

from antar.core.types import Modality

# Conservative hostname / IPv4 / bracket-free IPv6 pattern. Rejecting a leading
# '-' matters: the value is destined for an ssh command line.
_HOST_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-:]{0,252}$")
_USER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,31}$")


class GpuDevice(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, description="e.g. 'AMD Instinct MI300X'. Declared, not probed.")
    count: int = Field(default=1, ge=1)
    vram_gb: float | None = Field(default=None, gt=0)


class AmdCloudProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    ssh_host: str = Field(description="Hostname, IP address, or an alias from ~/.ssh/config.")
    ssh_user: str | None = Field(
        default=None, description="Omit when ssh_host is an SSH config alias that sets the user."
    )
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_key_path: Path | None = Field(
        default=None, description="Path to a private key outside the repository."
    )
    remote_workdir: str = Field(default="~/antar", pattern=r"^[A-Za-z0-9_./~\-]+$")
    rocm_version: str | None = Field(default=None, pattern=r"^\d+(\.\d+){1,2}$")
    gpus: tuple[GpuDevice, ...] = ()
    gpu_poll_interval_seconds: float = Field(
        default=10.0, ge=2.0, le=3600, description="Minimum time between amd-smi samples."
    )
    ssh_timeout_seconds: float = Field(default=20.0, gt=0, le=300)

    @field_validator("ssh_host")
    @classmethod
    def _valid_host(cls, value: str) -> str:
        if not _HOST_PATTERN.fullmatch(value):
            raise ValueError("ssh_host must be a hostname or IP address")
        return value

    @field_validator("ssh_user")
    @classmethod
    def _valid_user(cls, value: str | None) -> str | None:
        if value is not None and not _USER_PATTERN.fullmatch(value):
            raise ValueError("ssh_user must be a valid POSIX username")
        return value


_LOOPBACK_NAMES = frozenset({"localhost"})
_MODEL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._\-]*(/[A-Za-z0-9._\-]+)*$"


def is_loopback(host: str) -> bool:
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


class CloudModelConfig(BaseModel):
    """What the operator declares about a model the endpoint serves.

    vLLM's model list does not say whether a model accepts images, so that is
    declared here (or comes from Antar's catalog of verified models) and never guessed.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=_MODEL_ID_PATTERN, description="The served model name.")
    source: str | None = Field(
        default=None, pattern=_MODEL_ID_PATTERN, description="Hugging Face repository id."
    )
    revision: str | None = None
    modalities: tuple[Modality, ...] = (Modality.TEXT,)
    license: str | None = None


class CloudEndpointSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: HttpUrl = Field(
        description="vLLM API base URL including /v1, e.g. http://127.0.0.1:18000/v1."
    )
    api_key: SecretStr | None = Field(
        default=None, description="Matches the key vLLM was started with, if any."
    )
    trusted_hosts: tuple[str, ...] = Field(
        default=(),
        description="Non-loopback hosts the operator explicitly allows. They must use HTTPS.",
    )
    timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    generation_timeout_seconds: float = Field(default=600.0, gt=0)
    models: tuple[CloudModelConfig, ...] = ()
    vllm_image: str | None = Field(
        default=None, description="Container image the operator started, recorded as declared."
    )

    @model_validator(mode="after")
    def _trusted_destination(self) -> Self:
        url = self.base_url
        # The URL is shown in the API and dashboard, so it must not carry secrets.
        if url.username or url.password:
            raise ValueError("base_url must not contain credentials; use api_key instead")
        host = url.host or ""
        if is_loopback(host):
            return self
        if host.lower() not in {trusted.lower() for trusted in self.trusted_hosts}:
            raise ValueError(
                f"'{host}' is not a loopback address. Reach the server through an SSH tunnel, "
                "or list the host in cloud.trusted_hosts to allow it explicitly."
            )
        if url.scheme != "https":
            raise ValueError("a non-loopback cloud endpoint must use https")
        if self.api_key is None:
            raise ValueError("a non-loopback cloud endpoint must have an api_key")
        return self


class CloudCostSettings(BaseModel):
    """Operator-entered cost inputs. Antar reads no provider billing API."""

    model_config = ConfigDict(frozen=True)

    hourly_price_usd: float | None = Field(default=None, ge=0)
    credit_balance_usd: float | None = Field(default=None, ge=0)
    max_experiment_minutes: float = Field(
        default=30.0, gt=0, le=24 * 60, description="A comparison is stopped after this long."
    )
    warn_at_fraction: float = Field(
        default=0.8,
        gt=0,
        le=1,
        description="Warn once this share of the credit is estimated spent.",
    )
