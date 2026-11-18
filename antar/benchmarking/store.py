"""Filesystem store for benchmark reports: one JSON file per run, plus CSV export."""

import csv
import io
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from antar.benchmarking.report import ID_PATTERN, Aggregate, BenchmarkReport, ReportStatus
from antar.core.errors import AntarError, ExperimentNotFoundError

logger = logging.getLogger(__name__)

CSV_COLUMNS = (
    "index",
    "workload",
    "prompt_id",
    "phase",
    "ok",
    "error",
    "latency_ms",
    "first_chunk_ms",
    "prompt_tokens",
    "completion_tokens",
    "cached_prompt_tokens",
    "prompt_processing_ms",
    "generation_ms",
    "tokens_per_second",
    "finish_reason",
    "json_valid",
    "score",
    "score_method",
    "manual_score",
    "manual_notes",
)


class ReportSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    status: ReportStatus
    simulated: bool
    model: str
    quantization: str | None
    backend: str
    workloads: tuple[str, ...]
    overall: Aggregate | None
    started_at: datetime
    finished_at: datetime


def summarize(report: BenchmarkReport) -> ReportSummary:
    return ReportSummary(
        id=report.id,
        name=report.config.name,
        status=report.status,
        simulated=report.simulated,
        model=report.model.id,
        quantization=report.model.quantization,
        backend=report.backend,
        workloads=report.config.workloads,
        overall=next((item for item in report.aggregates if item.workload == "all"), None),
        started_at=report.started_at,
        finished_at=report.finished_at,
    )


def csv_cell(value: object) -> object:
    """Empty for unavailable values; text that a spreadsheet would run as a formula is quoted."""
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def to_csv(report: BenchmarkReport) -> str:
    """One row per request. Unavailable values are empty cells, never zero."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for run in report.runs:
        row = run.model_dump(exclude={"metrics", "response"})
        row.update(run.metrics.model_dump() if run.metrics else {})
        writer.writerow({key: csv_cell(value) for key, value in row.items()})
    return buffer.getvalue()


class BenchmarkStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, report_id: str) -> Path:
        if not re.fullmatch(ID_PATTERN, report_id):
            raise ExperimentNotFoundError(f"Invalid benchmark id '{report_id}'.")
        return self._root / f"{report_id}.json"

    def save(self, report: BenchmarkReport) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path(report.id)
        # Write beside the target, then swap, so a crash cannot leave a truncated report.
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        return path

    def get(self, report_id: str) -> BenchmarkReport:
        path = self._path(report_id)
        if not path.is_file():
            raise ExperimentNotFoundError(f"No benchmark with id '{report_id}'.")
        return self._load(path)

    def list(self) -> tuple[ReportSummary, ...]:
        if not self._root.is_dir():
            return ()
        summaries: list[ReportSummary] = []
        for path in self._root.glob("*.json"):
            try:
                summaries.append(summarize(self._load(path)))
            except AntarError as exc:
                # One damaged file must not hide every other result.
                logger.warning("Skipping benchmark report: %s", exc)
        return tuple(sorted(summaries, key=lambda item: item.started_at, reverse=True))

    def set_manual_evaluation(
        self, report_id: str, run_index: int, *, score: int | None, notes: str | None
    ) -> BenchmarkReport:
        report = self.get(report_id)
        if not any(run.index == run_index for run in report.runs):
            raise ExperimentNotFoundError(f"Benchmark '{report_id}' has no run {run_index}.")
        runs = tuple(
            run.model_copy(update={"manual_score": score, "manual_notes": notes})
            if run.index == run_index
            else run
            for run in report.runs
        )
        updated = report.model_copy(update={"runs": runs})
        self.save(updated)
        return updated

    @staticmethod
    def _load(path: Path) -> BenchmarkReport:
        try:
            return BenchmarkReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise AntarError(f"Benchmark report {path} is unreadable or invalid: {exc}") from exc
