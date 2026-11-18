import { bytesOrUnavailable, readingOrUnavailable } from "../../lib/cloud";
import { formatBytes, formatDateTime, formatDuration, formatElapsed, formatMoney, formatParameters } from "../../lib/format";
import type { BenchmarkReport, ComparisonReport, Side } from "../../lib/types";
import { Fact, LocationBadge, Tag, Value } from "../ui";

const NOT_STATED = "Not stated";

function SideFacts({ side, report, modelId }: { side: Side; report: BenchmarkReport | null; modelId: string }) {
  return (
    <section className={`min-w-0 rounded-md border border-line border-t-2 p-4 ${side === "local" ? "border-t-local" : "border-t-cloud"}`}>
      <h3 className="flex flex-wrap items-center justify-between gap-2">
        <LocationBadge location={side} />
        {report?.simulated && <Tag tone="warn">Simulated</Tag>}
      </h3>
      <p className="mt-2 font-mono text-sm break-all">{modelId}</p>
      {!report ? (
        <p className="mt-3 text-sm text-muted">This side did not run, so there is nothing recorded for it.</p>
      ) : (
        <dl className="mt-3">
          <Fact term="Ran on">
            {report.execution === null ? "Not recorded" : report.execution === "mock" ? "Mock backend, no inference" : report.execution === "cloud" ? "Cloud" : "This machine"}
          </Fact>
          <Fact term="Backend">
            {report.backend} {report.backend_version ?? ""}
          </Fact>
          <Fact term="Runtime">{report.model.runtime ?? NOT_STATED}</Fact>
          <Fact term="Weights">
            <span className="font-mono text-xs break-all">{report.model.checkpoint ?? NOT_STATED}</span>
          </Fact>
          <Fact term="Precision">{report.model.quantization ?? NOT_STATED}</Fact>
          <Fact term="Parameters">{formatParameters(report.model.parameter_count) ?? "Not published"}</Fact>
          <Fact term="Size">{report.model.size_bytes === null ? NOT_STATED : formatBytes(report.model.size_bytes)}</Fact>
          <Fact term="Context length">
            {report.model.context_length === null ? NOT_STATED : `${report.model.context_length.toLocaleString("en-US")} tokens`}
          </Fact>
          <Fact term="Revision">
            <span className="font-mono text-xs break-all">{report.model.revision ?? "Not pinned"}</span>
          </Fact>
          <Fact term="Hardware">
            {side === "cloud" && report.remote_gpus && report.remote_gpus.gpus.length > 0
              ? report.remote_gpus.gpus.map((gpu) => gpu.name ?? `GPU ${gpu.index}`).join(", ")
              : side === "cloud" && report.execution === "cloud"
                ? "GPU details not recorded"
                : `${report.hardware.cpu_model}, ${formatBytes(report.hardware.memory_total_bytes)}`}
          </Fact>
          <Fact term="Requests">
            {report.runs.length} sent, status {report.status}
          </Fact>
        </dl>
      )}
    </section>
  );
}

export function ModelFacts({ report }: { report: ComparisonReport }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <SideFacts side="local" report={report.local} modelId={report.config.local.model.id} />
      <SideFacts side="cloud" report={report.cloud} modelId={report.config.cloud.model.id} />
    </div>
  );
}

export function CloudSideDetails({ report }: { report: ComparisonReport }) {
  const { gpu, transport, usage } = report;
  return (
    <div className="grid gap-x-10 gap-y-6 lg:grid-cols-2">
      <section>
        <h3 className="text-sm font-medium">GPU usage during the cloud run</h3>
        <p className="mt-1 text-xs text-muted">Device-level, whole GPU — not per model or per request. Measured by amd-smi on the host.</p>
        {gpu ? (
          <>
            <dl className="mt-2">
              <Fact term="GPUs">{gpu.gpu_names.length > 0 ? `${gpu.gpu_count ?? gpu.gpu_names.length} × ${gpu.gpu_names.join(", ")}` : <Value>{readingOrUnavailable(gpu.gpu_count, "")}</Value>}</Fact>
              <Fact term="Samples">
                {gpu.samples}
                {gpu.interval_seconds !== null && `, every ${gpu.interval_seconds} s`}
              </Fact>
              <Fact term="Peak memory used"><Value>{bytesOrUnavailable(gpu.memory_used_peak_bytes)}</Value></Fact>
              <Fact term="Memory total"><Value>{bytesOrUnavailable(gpu.memory_total_bytes)}</Value></Fact>
              <Fact term="Mean utilization"><Value>{readingOrUnavailable(gpu.utilization_mean_percent, "%")}</Value></Fact>
              <Fact term="Peak utilization"><Value>{readingOrUnavailable(gpu.utilization_peak_percent, "%")}</Value></Fact>
              <Fact term="Peak power"><Value>{readingOrUnavailable(gpu.power_peak_watts, "W")}</Value></Fact>
              <Fact term="Driver"><Value>{gpu.driver_version ?? "Unavailable"}</Value></Fact>
              <Fact term="ROCm"><Value>{gpu.rocm_version ?? "Unavailable"}</Value></Fact>
            </dl>
            {gpu.unavailable.length > 0 && (
              <ul className="mt-2 space-y-1 text-xs text-muted">
                {gpu.unavailable.map((item) => (
                  <li key={item.metric}>
                    <span className="font-mono text-ink">{item.metric}</span>: {item.reason}
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p className="mt-2 text-sm text-muted">
            No GPU readings were taken during this run, so none are shown.
          </p>
        )}
      </section>

      <div className="space-y-6">
        <section>
          <h3 className="text-sm font-medium">Transport round trip</h3>
          {transport ? (
            <>
              <dl className="mt-2">
                <Fact term="Median"><Value>{formatDuration(transport.median_ms)}</Value></Fact>
                <Fact term="Samples">
                  {transport.samples_ms.length > 0 ? transport.samples_ms.map((sample) => formatDuration(sample)).join(", ") : "None"}
                </Fact>
              </dl>
              <p className="mt-2 text-xs text-muted">{transport.note}</p>
            </>
          ) : (
            <p className="mt-2 text-sm text-muted">
              Not measured: there was no cloud endpoint to send a health request to.
            </p>
          )}
        </section>

        <section>
          <h3 className="text-sm font-medium">Cloud usage and estimated cost</h3>
          <dl className="mt-2">
            <Fact term="Cloud side busy for">
              <Value>{usage.cloud_seconds === null ? "Unavailable" : usage.cloud_seconds < 1 ? formatDuration(usage.cloud_seconds * 1000) : formatElapsed(usage.cloud_seconds)}</Value>
            </Fact>
            <Fact term="Hourly price entered">
              {usage.hourly_price_usd === null ? "Not entered" : formatMoney(usage.hourly_price_usd)}
            </Fact>
            <Fact term="Estimated cost"><Value>{formatMoney(usage.estimated_cost_usd)}</Value></Fact>
          </dl>
          <p className="mt-2 text-xs text-muted">{usage.note}</p>
        </section>
      </div>
    </div>
  );
}

/** Everything needed to run the same comparison again. */
export function Reproducibility({ report }: { report: ComparisonReport }) {
  const workloads = (report.local ?? report.cloud)?.workloads ?? [];
  const config = report.config;
  return (
    <section>
      <h3 className="text-sm font-medium">Reproducibility</h3>
      <dl className="mt-2 grid gap-x-10 lg:grid-cols-2">
        <Fact term="Antar version">{report.antar_version}</Fact>
        <Fact term="Git commit">
          <span className="font-mono text-xs">{report.git_commit ?? "Not recorded"}</span>
        </Fact>
        <Fact term="Workload versions">
          {workloads.length > 0
            ? workloads.map((workload) => `${workload.id}@${workload.version}${workload.license ? ` (${workload.license})` : ""}`).join(", ")
            : config.workloads.join(", ")}
        </Fact>
        <Fact term="Settings">
          {config.max_tokens} tokens, temperature {config.temperature}, seed {config.seed ?? "none"}, reasoning{" "}
          {config.enable_thinking ? "on" : "off"}
        </Fact>
        <Fact term="Warm-up, measured passes">
          {config.warmup_runs}, {config.measured_runs}
        </Fact>
        <Fact term="Model-written code">{config.allow_code_execution ? "Allowed to run" : "Not run"}</Fact>
        <Fact term="Local model revision">
          <span className="font-mono text-xs break-all">{report.local?.model.revision ?? "Not pinned"}</span>
        </Fact>
        <Fact term="Cloud model revision">
          <span className="font-mono text-xs break-all">{report.cloud?.model.revision ?? "Not pinned"}</span>
        </Fact>
        <Fact term="Local backend">
          {report.local ? `${report.local.backend} ${report.local.backend_version ?? "(version not reported)"}` : "Did not run"}
        </Fact>
        <Fact term="Cloud backend">
          {report.cloud ? `${report.cloud.backend} ${report.cloud.backend_version ?? "(version not reported)"}` : "Did not run"}
        </Fact>
        <Fact term="vLLM image">
          {report.vllm_image ? (
            <>
              <span className="font-mono text-xs break-all">{report.vllm_image}</span>
              <span className="block text-2xs text-faint">As declared in the configuration, not probed</span>
            </>
          ) : (
            "Not declared"
          )}
        </Fact>
        <Fact term="Lemonade version">{report.lemonade_version ?? "Not reported"}</Fact>
        <Fact term="Started">{formatDateTime(report.started_at)}</Fact>
        <Fact term="Finished">{formatDateTime(report.finished_at)}</Fact>
      </dl>
    </section>
  );
}
