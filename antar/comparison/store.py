"""Filesystem store for comparison reports: one JSON file per comparison."""

import logging
import os
import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from antar.benchmarking.report import ID_PATTERN
from antar.comparison.report import ComparisonReport, ComparisonStatus
from antar.core.errors import AntarError, ExperimentNotFoundError

logger = logging.getLogger(__name__)


class ComparisonSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    status: ComparisonStatus
    simulated: bool
    local_model: str
    local_backend: str
    cloud_model: str
    cloud_backend: str
    workloads: tuple[str, ...]
    git_commit: str | None
    estimated_cost_usd: float | None
    started_at: datetime
    finished_at: datetime


def summarize(report: ComparisonReport) -> ComparisonSummary:
    config = report.config
    return ComparisonSummary(
        id=report.id,
        name=config.name,
        status=report.status,
        simulated=report.simulated,
        local_model=config.local.model.id,
        local_backend=config.local.backend,
        cloud_model=config.cloud.model.id,
        cloud_backend=config.cloud.backend,
        workloads=config.workloads,
        git_commit=report.git_commit,
        estimated_cost_usd=report.usage.estimated_cost_usd,
        started_at=report.started_at,
        finished_at=report.finished_at,
    )


class ComparisonStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, report_id: str) -> Path:
        if not re.fullmatch(ID_PATTERN, report_id):
            raise ExperimentNotFoundError(f"Invalid comparison id '{report_id}'.")
        return self._root / f"{report_id}.json"

    def save(self, report: ComparisonReport) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path(report.id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        return path

    def get(self, report_id: str) -> ComparisonReport:
        path = self._path(report_id)
        if not path.is_file():
            raise ExperimentNotFoundError(f"No comparison with id '{report_id}'.")
        return self._load(path)

    def list(self) -> tuple[ComparisonSummary, ...]:
        if not self._root.is_dir():
            return ()
        summaries: list[ComparisonSummary] = []
        for path in self._root.glob("*.json"):
            try:
                summaries.append(summarize(self._load(path)))
            except AntarError as exc:
                # One damaged file must not hide every other result.
                logger.warning("Skipping comparison report: %s", exc)
        return tuple(sorted(summaries, key=lambda item: item.started_at, reverse=True))

    @staticmethod
    def _load(path: Path) -> ComparisonReport:
        try:
            return ComparisonReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise AntarError(f"Comparison report {path} is unreadable or invalid: {exc}") from exc
