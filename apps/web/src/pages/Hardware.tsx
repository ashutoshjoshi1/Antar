import { Link } from "react-router";

import { Fact, Meter, PageHeader, Panel, QueryView, StatusPill } from "../components/ui";
import { useBackends, useSystem, useTelemetry } from "../lib/api";
import { formatBytes, formatCount, formatDuration, titleCase, usedFraction } from "../lib/format";
import type { HardwareProfile, Telemetry } from "../lib/types";

function describeMetric(metric: string): string {
  const [name, subject] = metric.split(":");
  const label = titleCase(name ?? metric);
  return subject ? `${label} (${subject})` : label;
}

function LiveTelemetry({ telemetry }: { telemetry: Telemetry }) {
  const backends = useBackends();
  const lemonade = backends.data?.find((backend) => backend.name === "lemonade");
  const { system, lemonade_stats: stats } = telemetry;
  const activeRequests = stats?.live?.active_requests ?? null;
  const used = system.memory_total_bytes - system.memory_available_bytes;

  return (
    <div className="mb-6 grid gap-6 lg:grid-cols-3">
      <Panel title="Inference right now">
        <dl>
          <Fact term="Lemonade">
            {lemonade ? <StatusPill availability={lemonade.availability} /> : "Checking…"}
          </Fact>
          <Fact term="Model in memory">
            {telemetry.loaded_models.length > 0 ? (
              telemetry.loaded_models.map((item) => (
                <span key={item.model} className="block font-mono text-xs">
                  {item.model}
                </span>
              ))
            ) : (
              <span className="text-muted">None</span>
            )}
          </Fact>
          <Fact term="Status">
            {telemetry.benchmark_running ? (
              <Link to="/benchmarks" className="text-local hover:underline">
                Benchmark running
              </Link>
            ) : activeRequests === null ? (
              <span className="text-faint">Unavailable</span>
            ) : activeRequests > 0 ? (
              `Generating (${activeRequests} active)`
            ) : (
              "Idle"
            )}
          </Fact>
        </dl>
        {lemonade && lemonade.availability !== "available" && (
          <p className="mt-3 text-sm text-muted">{lemonade.detail}</p>
        )}
      </Panel>

      <Panel title="Measured now">
        <div className="space-y-5">
          <Meter label="CPU in use" fraction={system.cpu_percent / 100} detail={`${system.cpu_percent.toFixed(0)}%`} />
          <Meter
            label="Memory in use"
            fraction={usedFraction(system.memory_total_bytes, system.memory_available_bytes)}
            detail={`${formatBytes(used)} of ${formatBytes(system.memory_total_bytes)}`}
          />
          <dl>
            {system.processes.map((process) => (
              <Fact key={process.pid} term={`${process.label} memory`}>
                {formatBytes(process.rss_bytes)}
              </Fact>
            ))}
          </dl>
        </div>
      </Panel>

      <Panel title="Lemonade server counters">
        {stats ? (
          <dl>
            <Fact term="Latest request speed">{formatCount(stats.tokens_per_second, "tokens/s")}</Fact>
            <Fact term="Latest time to first token">
              {formatDuration(stats.time_to_first_token === null ? null : stats.time_to_first_token * 1000)}
            </Fact>
            <Fact term="Requests since start">{formatCount(stats.request_count_total)}</Fact>
            <Fact term="Tokens generated since start">{formatCount(stats.output_tokens_total)}</Fact>
          </dl>
        ) : (
          <p className="text-sm text-muted">Unavailable while Lemonade is not reachable.</p>
        )}
        <p className="mt-3 text-xs text-faint">
          These describe the whole server and whichever request it served last, from any client.
          Per-request numbers are on the Playground and Benchmarks pages.
        </p>
      </Panel>

      <Panel title="Not available on this machine" className="lg:col-span-3">
        <ul className="grid gap-x-10 gap-y-2 text-sm sm:grid-cols-2">
          {system.unavailable.map((item) => (
            <li key={item.metric}>
              <span className="text-ink">{describeMetric(item.metric)}</span>
              <span className="block text-xs text-muted">{item.reason}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

function Profile({ profile }: { profile: HardwareProfile }) {
  const memoryUsed = profile.memory_total_bytes - profile.memory_available_bytes;
  const diskUsed = profile.disk_total_bytes - profile.disk_free_bytes;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel title="Device">
        <dl>
          <Fact term="Hostname">{profile.hostname}</Fact>
          <Fact term="Processor">{profile.cpu_model}</Fact>
          <Fact term="Cores">
            {profile.cpu_physical_cores ?? "—"} physical, {profile.cpu_logical_cores ?? "—"} logical
          </Fact>
          <Fact term="Operating system">
            {profile.os} {profile.os_version}
          </Fact>
          <Fact term="Architecture">{profile.architecture}</Fact>
          <Fact term="Python">{profile.python_version}</Fact>
        </dl>
      </Panel>

      <Panel title="Capacity right now">
        <div className="space-y-6">
          <Meter
            label="Memory in use"
            fraction={usedFraction(profile.memory_total_bytes, profile.memory_available_bytes)}
            detail={`${formatBytes(memoryUsed)} of ${formatBytes(profile.memory_total_bytes)}`}
          />
          <Meter
            label="Disk in use"
            fraction={usedFraction(profile.disk_total_bytes, profile.disk_free_bytes)}
            detail={`${formatBytes(diskUsed)} of ${formatBytes(profile.disk_total_bytes)}`}
          />
          <p className="text-xs text-faint">
            {formatBytes(profile.memory_available_bytes)} of memory and{" "}
            {formatBytes(profile.disk_free_bytes)} of disk are free on the API's working volume.
          </p>
        </div>
      </Panel>

      <Panel title="Accelerators">
        {profile.accelerators.length === 0 ? (
          <p className="text-sm text-muted">
            No accelerator detected. GPU enumeration currently covers macOS only; on Linux, see the
            runtimes list for ROCm or CUDA tooling.
          </p>
        ) : (
          <ul className="space-y-4">
            {profile.accelerators.map((accelerator, index) => (
              <li key={`${accelerator.name}-${index}`}>
                <p className="font-medium">{accelerator.name}</p>
                <p className="mt-1 text-sm text-muted">
                  {[
                    accelerator.vendor,
                    accelerator.cores !== null ? `${accelerator.cores} GPU cores` : null,
                    accelerator.shares_system_memory
                      ? "shares system memory"
                      : accelerator.memory_bytes !== null
                        ? formatBytes(accelerator.memory_bytes)
                        : "memory not reported",
                  ]
                    .filter(Boolean)
                    .join(", ")}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Compute runtimes">
        <ul className="space-y-3">
          {profile.runtimes.map((runtime) => (
            <li key={runtime.name} className="grid grid-cols-[1.25rem_1fr] gap-x-2">
              <span
                aria-hidden
                className={`mt-1.5 size-2 rounded-full ${runtime.available ? "bg-ok" : "bg-faint"}`}
              />
              <div>
                <p className="text-sm">
                  <span className="font-mono">{runtime.name}</span>
                  {runtime.version && <span className="text-muted"> {runtime.version}</span>}
                  <span className="sr-only">{runtime.available ? " available" : " not available"}</span>
                </p>
                <p className="text-xs text-muted">{runtime.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

export function Hardware() {
  const system = useSystem();
  const telemetry = useTelemetry();
  return (
    <>
      <PageHeader
        title="System"
        summary="Live inference status and what this machine reports about itself. Anything the operating system does not expose is listed as unavailable, not estimated."
        actions={
          <button
            type="button"
            onClick={() => void system.refetch()}
            className="rounded-md border border-line px-3 py-1.5 text-sm hover:border-muted active:bg-raised"
          >
            {system.isFetching ? "Detecting…" : "Detect again"}
          </button>
        }
      />
      <QueryView query={telemetry}>{(data) => <LiveTelemetry telemetry={data} />}</QueryView>
      <QueryView query={system}>{(data) => <Profile profile={data} />}</QueryView>
    </>
  );
}
