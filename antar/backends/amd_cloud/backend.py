"""AMD ROCm cloud backend — interface and configuration validation only.

No remote execution exists yet. This backend never opens a network connection
and never starts a paid resource; it only reports whether a profile has been
configured.
"""

from typing import ClassVar

from antar.backends.amd_cloud.config import AmdCloudProfile
from antar.backends.base import (
    Availability,
    BackendKind,
    BackendStatus,
    Capability,
    RuntimeBackend,
    SupportLevel,
)
from antar.core.types import Modality
from antar.models.spec import ModelSpec


class AmdCloudBackend(RuntimeBackend):
    name: ClassVar[str] = "amd_cloud"
    display_name: ClassVar[str] = "AMD cloud (ROCm)"
    kind: ClassVar[BackendKind] = BackendKind.CLOUD

    def __init__(self, profile: AmdCloudProfile | None) -> None:
        self._profile = profile

    async def status(self) -> BackendStatus:
        if self._profile is None:
            return BackendStatus(
                name=self.name,
                display_name=self.display_name,
                kind=self.kind,
                availability=Availability.NOT_CONFIGURED,
                detail="No AMD cloud profile configured. See docs/installation/amd-cloud.md.",
            )
        profile = self._profile
        return BackendStatus(
            name=self.name,
            display_name=self.display_name,
            kind=self.kind,
            availability=Availability.NOT_IMPLEMENTED,
            detail=(
                f"Profile '{profile.name}' is valid, but remote execution is not implemented. "
                "No connection was attempted."
            ),
            endpoint=f"ssh://{profile.ssh_user}@{profile.ssh_host}:{profile.ssh_port}",
        )

    def capabilities(self) -> tuple[Capability, ...]:
        return tuple(
            Capability(
                modality=modality,
                support=SupportLevel.PLANNED,
                note="Remote ROCm execution is on the roadmap; nothing runs today.",
            )
            for modality in Modality
        )

    async def list_models(self) -> tuple[ModelSpec, ...]:
        return ()
