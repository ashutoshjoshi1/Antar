"""Benchmark configuration."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from antar.benchmarking.workloads import get_workload
from antar.core.errors import CapabilityNotSupportedError
from antar.models.spec import ModelRef

LoadPolicy = Literal["keep", "reload"]


class BenchmarkConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    model: ModelRef
    backend: str = Field(min_length=1)
    workloads: tuple[str, ...] = Field(min_length=1, description="Built-in workload ids.")
    warmup_runs: int = Field(
        default=1, ge=0, le=20, description="Unmeasured requests before each workload."
    )
    measured_runs: int = Field(
        default=3, ge=1, le=100, description="Measured passes over each workload's prompts."
    )
    max_tokens: int = Field(default=256, ge=1, le=16384)
    temperature: float = Field(default=0.0, ge=0, le=2)
    seed: int | None = Field(default=42, ge=0)
    enable_thinking: bool | None = Field(
        default=False,
        description="Reasoning is off by default so output length is comparable across models.",
    )
    load_policy: LoadPolicy = Field(
        default="keep",
        description=(
            "'keep' uses the model as loaded. 'reload' unloads and reloads it first, "
            "measuring load time and a cold first request."
        ),
    )
    # Requests run one at a time so each measurement has the hardware to itself.
    concurrency: Literal[1] = 1

    @field_validator("workloads")
    @classmethod
    def _known_unique_workloads(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for workload_id in value:
            try:
                get_workload(workload_id)
            except CapabilityNotSupportedError as exc:
                raise ValueError(str(exc)) from exc
        if len(set(value)) != len(value):
            raise ValueError("workloads must not repeat")
        return value
