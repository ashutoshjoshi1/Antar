"""Exports of a comparison: CSV of every request, and a Markdown report for people."""

import csv
import io
import re
from collections.abc import Sequence

from antar.benchmarking.report import BenchmarkReport
from antar.benchmarking.store import CSV_COLUMNS, csv_cell
from antar.comparison.report import ComparisonReport, ComparisonRow

_NA = "n/a"
_MEASURED_BY = {"antar": "Antar API", "backend": "backend", "scorer": "Antar scorer"}
_GIB = 1024**3


def to_csv(report: ComparisonReport) -> str:
    """One row per request, both sides. Unavailable values are empty cells, never zero."""
    buffer = io.StringIO()
    columns = ("side", "backend", "model", *CSV_COLUMNS)
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for side, benchmark in (("local", report.local), ("cloud", report.cloud)):
        if benchmark is None:
            continue
        for run in benchmark.runs:
            row = run.model_dump(exclude={"metrics", "response"})
            row.update(run.metrics.model_dump() if run.metrics else {})
            row.update(side=side, backend=benchmark.backend, model=benchmark.model.id)
            writer.writerow({key: csv_cell(value) for key, value in row.items()})
    return buffer.getvalue()


def _value(value: float | None, unit: str | None) -> str:
    if value is None:
        return _NA
    if unit == "ratio":
        return f"{value:.1%}"
    return f"{value:,.1f}" if unit in ("ms", "tok/s", "tokens") else f"{value:g}"


def _with_unit(value: float | None, unit: str | None) -> str:
    text = _value(value, unit)
    return f"{text} {unit}" if value is not None and unit not in (None, "ratio") else text


def _cell(text: object) -> str:
    if text is None:
        return _NA
    # Values can come from a remote server; keep them from forming links, images, or cells.
    return re.sub(r"[|\[\]<>`!]", lambda match: "\\" + match.group(), str(text)).replace("\n", " ")


def _table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(item) for item in row) + " |" for row in rows]
    return [*lines, ""]


def _side(benchmark: BenchmarkReport | None) -> list[object]:
    if benchmark is None:
        return [_NA] * 7
    model = benchmark.model
    return [
        model.id,
        model.revision,
        model.quantization,
        f"{model.parameter_count / 1e9:.2f} B" if model.parameter_count else None,
        f"{benchmark.backend} ({model.runtime or _NA})",
        benchmark.backend_version,
        benchmark.execution.value if benchmark.execution else None,
    ]


def _chart(title: str, unit: str, row: ComparisonRow | None) -> list[str]:
    """A Mermaid bar chart, drawn only when both sides have the value."""
    if row is None or row.local is None or row.cloud is None:
        return []
    top = max(row.local, row.cloud) * 1.15 or 1
    return [
        "```mermaid",
        "xychart-beta",
        f'    title "{title}"',
        '    x-axis ["local", "cloud"]',
        f'    y-axis "{unit}" 0 --> {top:.0f}',
        f"    bar [{row.local:.1f}, {row.cloud:.1f}]",
        "```",
        "",
    ]


def to_markdown(report: ComparisonReport) -> str:
    config = report.config
    lines = [f"# {config.name}", ""]
    if report.simulated:
        lines += ["> **Simulated.** A mock backend produced these responses. No model ran.", ""]
    lines += [
        f"Comparison `{report.id}` — status **{report.status}**. "
        f"Started {report.started_at:%Y-%m-%d %H:%M:%S} UTC, "
        f"finished {report.finished_at:%Y-%m-%d %H:%M:%S} UTC.",
        "",
    ]
    if report.failure:
        lines += [f"**Failure:** {report.failure}", ""]
    lines += [
        "> This is not a hardware-normalized comparison. The sides differ in model, "
        "precision, hardware, and network path.",
        "",
        "## What ran",
        "",
    ]
    facts = (
        "Model",
        "Revision",
        "Precision",
        "Parameters",
        "Backend",
        "Backend version",
        "Location",
    )
    lines += _table(
        ("", "Local", "Cloud"),
        [list(row) for row in zip(facts, _side(report.local), _side(report.cloud), strict=True)],
    )

    lines += ["## Results", ""]
    for workload in ("all", *config.workloads):
        rows = [row for row in report.rows if row.workload == workload]
        if not rows:
            continue
        lines += [f"### {'All workloads' if workload == 'all' else workload}", ""]
        lines += _table(
            ("Metric", "Local", "Cloud", "Scope", "Measured by"),
            [
                (
                    row.label,
                    _with_unit(row.local, row.unit),
                    _with_unit(row.cloud, row.unit),
                    row.scope.replace("_", "-"),
                    _MEASURED_BY[row.measured_by],
                )
                for row in rows
            ],
        )

    overall = {row.metric: row for row in report.rows if row.workload == "all"}
    charts = _chart(
        "End-to-end latency, median (ms)", "ms", overall.get("latency_ms_median")
    ) + _chart(
        "Tokens per second after the first token, median",
        "tok/s",
        overall.get("decode_tokens_per_second_median"),
    )
    if charts:
        lines += ["## Charts", "", *charts]

    lines += ["## Cloud hardware and usage", ""]
    gpu = report.gpu
    if gpu is None:
        lines += [
            "GPU readings: not available (no SSH host configured, or the cloud side did not run).",
            "",
        ]
    else:
        lines += _table(
            ("Reading", "Value"),
            [
                (
                    "GPUs",
                    f"{gpu.gpu_count} x {', '.join(gpu.gpu_names) or 'unnamed'}"
                    if gpu.gpu_count
                    else None,
                ),
                (
                    "Total GPU memory",
                    f"{gpu.memory_total_bytes / _GIB:.1f} GiB" if gpu.memory_total_bytes else None,
                ),
                (
                    "Peak GPU memory used",
                    f"{gpu.memory_used_peak_bytes / _GIB:.1f} GiB"
                    if gpu.memory_used_peak_bytes is not None
                    else None,
                ),
                (
                    "Mean GPU utilization",
                    f"{gpu.utilization_mean_percent:.0f} %"
                    if gpu.utilization_mean_percent is not None
                    else None,
                ),
                (
                    "Peak power",
                    f"{gpu.power_peak_watts:.0f} W" if gpu.power_peak_watts is not None else None,
                ),
                ("amdgpu driver", gpu.driver_version),
                ("ROCm", gpu.rocm_version),
                (
                    "Samples",
                    f"{gpu.samples} (every {gpu.interval_seconds:g} s)"
                    if gpu.interval_seconds
                    else gpu.samples,
                ),
            ],
        )
    usage = report.usage
    transport = report.transport
    lines += _table(
        ("Item", "Value"),
        [
            ("vLLM image (declared)", report.vllm_image),
            ("Lemonade version", report.lemonade_version),
            (
                "Path round trip, median",
                f"{transport.median_ms:.1f} ms"
                if transport and transport.median_ms is not None
                else None,
            ),
            (
                "Cloud time used by this run",
                f"{usage.cloud_seconds:.0f} s" if usage.cloud_seconds is not None else None,
            ),
            (
                "Hourly price (entered)",
                f"${usage.hourly_price_usd:.2f}" if usage.hourly_price_usd is not None else None,
            ),
            (
                "Estimated cost of this run",
                f"${usage.estimated_cost_usd:.4f}"
                if usage.estimated_cost_usd is not None
                else None,
            ),
        ],
    )
    lines += [usage.note, ""]

    measured = report.local or report.cloud
    versions = (
        ", ".join(f"`{item.id}` v{item.version}" for item in measured.workloads)
        if measured
        else _NA
    )
    lines += [
        "## Methodology",
        "",
        f"- Workloads: {versions}. Each side ran the same prompts, in the same order, one "
        "request at a time.",
        f"- {config.warmup_runs} warm-up request(s) per workload, then {config.measured_runs} "
        "measured pass(es) over every prompt.",
        f"- Generation settings: max_tokens={config.max_tokens}, "
        f"temperature={config.temperature:g}, seed={config.seed}, "
        f"enable_thinking={config.enable_thinking}.",
        "- The local side ran first, then the cloud side. Neither model was reloaded.",
        f"- Antar {report.antar_version}, commit `{report.git_commit or _NA}`.",
        "",
        "## Limitations",
        "",
        *[f"- {caveat}" for caveat in report.caveats],
        "",
    ]
    return "\n".join(lines)
