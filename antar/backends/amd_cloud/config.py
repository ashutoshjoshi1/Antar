"""AMD cloud execution profile.

A profile describes a remote AMD GPU host that *you* have provisioned. Antar
makes no assumption about which GPU, storage, or network access your account
provides — everything is declared here and validated, nothing is discovered by
connecting.
"""

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    ssh_host: str
    ssh_user: str
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_key_path: Path | None = Field(
        default=None, description="Path to a private key outside the repository."
    )
    remote_workdir: str = Field(default="~/antar", pattern=r"^[A-Za-z0-9_./~\-]+$")
    rocm_version: str | None = Field(default=None, pattern=r"^\d+(\.\d+){1,2}$")
    gpus: tuple[GpuDevice, ...] = ()

    @field_validator("ssh_host")
    @classmethod
    def _valid_host(cls, value: str) -> str:
        if not _HOST_PATTERN.fullmatch(value):
            raise ValueError("ssh_host must be a hostname or IP address")
        return value

    @field_validator("ssh_user")
    @classmethod
    def _valid_user(cls, value: str) -> str:
        if not _USER_PATTERN.fullmatch(value):
            raise ValueError("ssh_user must be a valid POSIX username")
        return value
