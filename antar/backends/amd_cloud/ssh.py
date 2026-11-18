"""Run fixed, read-only commands on the configured AMD host over SSH.

Only command strings defined in this package are ever sent; nothing from an
HTTP request or a model reaches the remote shell. Authentication is whatever
the operator's own ``ssh`` is configured with (agent, ``~/.ssh/config``, or the
key path in the profile) — Antar never reads a private key and never prompts
(``BatchMode=yes``).
"""

import asyncio
import shutil
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from antar.backends.amd_cloud.config import AmdCloudProfile
from antar.core.errors import BackendUnavailableError


class CommandResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    exit_code: int
    stdout: str
    stderr: str


class RemoteRunner(Protocol):
    async def run(self, command: str, *, stdin: bytes | None = None) -> CommandResult:
        """Run ``command`` remotely. Raises ``BackendUnavailableError`` if unreachable."""
        ...


def ssh_arguments(profile: AmdCloudProfile) -> list[str]:
    """The ssh argument list up to and including the target."""
    arguments = [
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={max(1, round(profile.ssh_timeout_seconds))}",
        "-p",
        str(profile.ssh_port),
    ]
    if profile.ssh_key_path is not None:
        arguments += ["-i", str(profile.ssh_key_path.expanduser())]
    target = f"{profile.ssh_user}@{profile.ssh_host}" if profile.ssh_user else profile.ssh_host
    # "--" ends option parsing, so the target can never be read as an ssh flag.
    return [*arguments, "--", target]


class SshRunner:
    def __init__(self, profile: AmdCloudProfile) -> None:
        self._profile = profile

    async def run(self, command: str, *, stdin: bytes | None = None) -> CommandResult:
        ssh = shutil.which("ssh")
        if ssh is None:
            raise BackendUnavailableError("No ssh client is installed on this machine.")
        timeout = self._profile.ssh_timeout_seconds
        process = await asyncio.create_subprocess_exec(
            ssh,
            *ssh_arguments(self._profile),
            command,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(stdin), timeout * 3)
        except TimeoutError as exc:
            raise BackendUnavailableError(
                f"The AMD host did not answer over SSH within {timeout * 3:g}s."
            ) from exc
        finally:
            # Also on cancellation (a closed browser tab): never leave ssh running.
            if process.returncode is None:
                process.kill()
                await process.wait()
        result = CommandResult(
            exit_code=process.returncode if process.returncode is not None else -1,
            stdout=stdout.decode("utf-8", "replace"),
            stderr=stderr.decode("utf-8", "replace"),
        )
        # ssh itself exits 255 when it cannot connect or authenticate.
        if result.exit_code == 255:
            reason = result.stderr.strip().splitlines()[-1:] or ["no error message"]
            raise BackendUnavailableError(f"SSH to the AMD host failed: {reason[0]}")
        return result
