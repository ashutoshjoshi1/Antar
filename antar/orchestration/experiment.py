"""The standard experiment record and its filesystem store.

One record captures everything needed to reproduce and audit an optimization
experiment. Records are written as one JSON file each; the store never invents
or backfills values.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from antar.core.errors import AntarError, ExperimentNotFoundError
from antar.core.types import utc_now
from antar.deployment.manifest import ArtifactRef
from antar.evaluation.result import DatasetRef, EvaluationResult
from antar.hardware.profile import HardwareProfile
from antar.models.spec import ModelRef
from antar.optimization.job import TechniqueConfig

logger = logging.getLogger(__name__)

_ID_PATTERN = r"^[a-z0-9][a-z0-9_\-]{0,63}$"

SCHEMA_VERSION = 1


class ExperimentRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    id: str = Field(pattern=_ID_PATTERN)
    name: str = Field(min_length=1)
    model: ModelRef
    dataset: DatasetRef | None = None
    hardware: HardwareProfile
    backend: str
    runtime_version: str | None = Field(
        default=None, description="Version reported by the backend at execution time."
    )
    optimization: tuple[TechniqueConfig, ...] = ()
    seed: int | None = None
    baseline: EvaluationResult | None = None
    optimized: EvaluationResult | None = None
    artifacts: tuple[ArtifactRef, ...] = ()
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    @property
    def simulated(self) -> bool:
        return any(
            result is not None and result.simulated for result in (self.baseline, self.optimized)
        )


class ExperimentStore:
    """Stores experiment records as ``<root>/<id>.json``."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, experiment_id: str) -> Path:
        if not re.fullmatch(_ID_PATTERN, experiment_id):
            raise ExperimentNotFoundError(f"Invalid experiment id '{experiment_id}'.")
        return self._root / f"{experiment_id}.json"

    def save(self, record: ExperimentRecord) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path(record.id)
        path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path

    def get(self, experiment_id: str) -> ExperimentRecord:
        path = self._path(experiment_id)
        if not path.is_file():
            raise ExperimentNotFoundError(f"No experiment with id '{experiment_id}'.")
        return self._load(path)

    def list(self) -> tuple[ExperimentRecord, ...]:
        if not self._root.is_dir():
            return ()
        records: list[ExperimentRecord] = []
        for path in sorted(self._root.glob("*.json")):
            try:
                records.append(self._load(path))
            except AntarError as exc:
                # One damaged file must not hide every other experiment.
                logger.warning("Skipping experiment record: %s", exc)
        return tuple(sorted(records, key=lambda record: record.started_at, reverse=True))

    @staticmethod
    def _load(path: Path) -> ExperimentRecord:
        try:
            return ExperimentRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise AntarError(f"Experiment record {path} is unreadable or invalid: {exc}") from exc
