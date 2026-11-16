"""Benchmark configuration. The benchmark runner itself is not implemented yet."""

from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from antar.core.types import Modality, Task
from antar.evaluation.result import DatasetRef
from antar.modalities.catalog import metric_keys_for
from antar.models.spec import ModelRef


class BenchmarkConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    model: ModelRef
    backend: str
    modality: Modality
    task: Task
    dataset: DatasetRef | None = None
    metrics: tuple[str, ...] = Field(min_length=1, description="Metric keys to collect.")
    warmup_runs: int = Field(default=1, ge=0)
    measured_runs: int = Field(default=5, ge=1)
    concurrency: int = Field(default=1, ge=1)
    seed: int | None = None
    output_dir: Path | None = Field(
        default=None, description="Defaults to the configured benchmarks directory."
    )

    @model_validator(mode="after")
    def _metrics_match_modality(self) -> Self:
        unknown = sorted(set(self.metrics) - metric_keys_for(self.modality))
        if unknown:
            raise ValueError(
                f"Metrics not defined for the {self.modality.value} modality: {', '.join(unknown)}"
            )
        return self
