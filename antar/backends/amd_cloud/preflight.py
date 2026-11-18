"""Remote environment preflight: run ``scripts/cloud/check_environment.sh`` on the host.

The script is read-only. It is piped to ``bash -s`` over SSH and answers in a
line format this module parses:

    ANTAR_CHECK <TAB> id <TAB> pass|warn|fail|skip <TAB> detail <TAB> remediation
    ANTAR_FACT  <TAB> key <TAB> value
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from antar.backends.amd_cloud.ssh import RemoteRunner
from antar.core.errors import BackendRequestError, BackendUnavailableError
from antar.core.types import utc_now

CheckStatus = Literal["pass", "warn", "fail", "skip"]
_STATUSES: frozenset[str] = frozenset({"pass", "warn", "fail", "skip"})

PREFLIGHT_SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts" / "cloud" / "check_environment.sh"
)
PREFLIGHT_COMMAND = "bash -s -- --machine"


class PreflightCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: CheckStatus
    detail: str
    remediation: str | None = None


class PreflightReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    checked_at: datetime = Field(default_factory=utc_now)
    checks: tuple[PreflightCheck, ...]
    facts: dict[str, str]

    @property
    def ok(self) -> bool:
        return bool(self.checks) and not any(check.status == "fail" for check in self.checks)


def parse_preflight(output: str) -> PreflightReport:
    checks: list[PreflightCheck] = []
    facts: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.rstrip("\r").split("\t")
        if fields[0] == "ANTAR_CHECK" and len(fields) >= 4 and fields[2] in _STATUSES:
            remediation = fields[4].strip() if len(fields) > 4 else ""
            checks.append(
                PreflightCheck(
                    id=fields[1],
                    status=fields[2],
                    detail=fields[3],
                    remediation=remediation or None,
                )
            )
        elif fields[0] == "ANTAR_FACT" and len(fields) >= 3:
            facts[fields[1]] = fields[2]
    return PreflightReport(checks=tuple(checks), facts=facts)


async def run_preflight(runner: RemoteRunner, script: Path = PREFLIGHT_SCRIPT) -> PreflightReport:
    try:
        source = await asyncio.to_thread(script.read_bytes)
    except OSError as exc:
        raise BackendUnavailableError(
            "scripts/cloud/check_environment.sh was not found. Run Antar from a source checkout."
        ) from exc
    result = await runner.run(PREFLIGHT_COMMAND, stdin=source)
    report = parse_preflight(result.stdout)
    if not report.checks:
        raise BackendRequestError(
            "The preflight script produced no results on the AMD host "
            f"(exit code {result.exit_code}). Is bash available there?"
        )
    return report
