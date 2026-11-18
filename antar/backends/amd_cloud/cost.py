"""Cloud usage and cost estimates from numbers the operator enters.

Antar has no provider billing API and cannot see whether an instance exists.
Everything here is arithmetic on a start time and an hourly price that a
person typed in. "Stopped" means the operator said so — Antar never claims a
machine was stopped or destroyed.
"""

import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from antar.backends.amd_cloud.config import CloudCostSettings
from antar.core.errors import AntarError
from antar.core.types import utc_now


class CloudSession(BaseModel):
    """The operator's record of the paid instance. Stored locally; no secrets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hourly_price_usd: float | None = Field(default=None, ge=0)
    credit_balance_usd: float | None = Field(default=None, ge=0)
    instance_started_at: datetime | None = None
    instance_stopped_at: datetime | None = Field(
        default=None, description="When the operator says billing stopped. Not verified."
    )

    @model_validator(mode="after")
    def _ordered(self) -> "CloudSession":
        for moment in (self.instance_started_at, self.instance_stopped_at):
            if moment is not None and moment.tzinfo is None:
                raise ValueError("timestamps must include a timezone")
        if self.instance_stopped_at and not self.instance_started_at:
            raise ValueError("a stop time needs a start time")
        if (
            self.instance_started_at
            and self.instance_stopped_at
            and self.instance_stopped_at < self.instance_started_at
        ):
            raise ValueError("the instance cannot stop before it started")
        return self


class CostEstimate(BaseModel):
    model_config = ConfigDict(frozen=True)

    hourly_price_usd: float | None
    credit_balance_usd: float | None
    instance_started_at: datetime | None
    instance_stopped_at: datetime | None
    running: bool = Field(description="A start time is recorded and no stop time.")
    elapsed_seconds: float | None
    estimated_spend_usd: float | None
    estimated_remaining_usd: float | None
    estimated_hours_remaining: float | None
    max_experiment_minutes: float
    warnings: tuple[str, ...]


def duration_cost(seconds: float, hourly_price_usd: float | None) -> float | None:
    return None if hourly_price_usd is None else seconds / 3600 * hourly_price_usd


def estimate_cost(
    session: CloudSession, settings: CloudCostSettings, *, now: datetime | None = None
) -> CostEstimate:
    moment = now or utc_now()
    price = session.hourly_price_usd
    balance = session.credit_balance_usd
    started, stopped = session.instance_started_at, session.instance_stopped_at
    running = started is not None and stopped is None
    elapsed = max(0.0, ((stopped or moment) - started).total_seconds()) if started else None
    spend = duration_cost(elapsed, price) if elapsed is not None else None
    remaining = balance - spend if balance is not None and spend is not None else None

    warnings: list[str] = []
    if price is None:
        warnings.append("No hourly price entered, so spending cannot be estimated.")
    if started is None:
        warnings.append("No instance start time entered, so elapsed time is unknown.")
    if remaining is not None and balance:
        if remaining <= 0:
            warnings.append("Estimated spending has reached the entered credit balance.")
        elif spend is not None and spend >= balance * settings.warn_at_fraction:
            warnings.append(
                f"Estimated spending has passed {settings.warn_at_fraction:.0%} of the credit."
            )
    if running:
        warnings.append(
            "The instance is recorded as running. It bills until you stop it with your provider."
        )
    return CostEstimate(
        hourly_price_usd=price,
        credit_balance_usd=balance,
        instance_started_at=started,
        instance_stopped_at=stopped,
        running=running,
        elapsed_seconds=elapsed,
        estimated_spend_usd=spend,
        estimated_remaining_usd=remaining,
        estimated_hours_remaining=max(0.0, remaining) / price
        if remaining is not None and price
        else None,
        max_experiment_minutes=settings.max_experiment_minutes,
        warnings=tuple(warnings),
    )


class CloudSessionStore:
    """``<root>/session.json``. Falls back to the configured defaults when absent."""

    def __init__(self, root: Path, defaults: CloudCostSettings) -> None:
        self._path = root / "session.json"
        self._defaults = defaults

    def load(self) -> CloudSession:
        if not self._path.is_file():
            return CloudSession(
                hourly_price_usd=self._defaults.hourly_price_usd,
                credit_balance_usd=self._defaults.credit_balance_usd,
            )
        try:
            return CloudSession.model_validate_json(self._path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise AntarError(f"Cloud session file {self._path} is unreadable: {exc}") from exc

    def save(self, session: CloudSession) -> CloudSession:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".json.tmp")
        temporary.write_text(session.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self._path)
        return session
