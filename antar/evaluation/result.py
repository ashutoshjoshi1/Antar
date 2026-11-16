"""Evaluation results: measured values tied to how they were measured."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from antar.core.types import Modality, Task, utc_now
from antar.modalities.catalog import metric_keys_for
from antar.models.spec import ModelRef


class DatasetRef(BaseModel):
    """A dataset pinned tightly enough to reproduce an evaluation."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    version: str = Field(min_length=1, description="Revision, commit hash, or release tag.")
    license: str = Field(min_length=1, description="SPDX id or license name of the dataset.")
    split: str | None = None
    num_samples: int | None = Field(default=None, ge=1)


class MetricValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str = Field(description="A metric key from the modality catalog.")
    value: float = Field(allow_inf_nan=False)
    unit: str | None = None


class EvaluationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: ModelRef
    backend: str
    modality: Modality
    task: Task
    dataset: DatasetRef | None = Field(
        default=None, description="None only for pure performance measurements."
    )
    methodology: str = Field(
        min_length=1, description="How the numbers were obtained: prompts, runs, aggregation."
    )
    metrics: tuple[MetricValue, ...] = Field(min_length=1)
    simulated: bool = Field(
        default=False, description="True if any input came from a mock backend."
    )
    measured_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _metrics_match_modality(self) -> Self:
        allowed = metric_keys_for(self.modality)
        unknown = sorted({metric.key for metric in self.metrics} - allowed)
        if unknown:
            raise ValueError(
                f"Metrics not defined for the {self.modality.value} modality: {', '.join(unknown)}"
            )
        return self
