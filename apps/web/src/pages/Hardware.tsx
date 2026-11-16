import { Fact, Meter, PageHeader, Panel, QueryView } from "../components/ui";
import { useSystem } from "../lib/api";
import { formatBytes, usedFraction } from "../lib/format";
import type { HardwareProfile } from "../lib/types";

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
  return (
    <>
      <PageHeader
        title="Hardware"
        summary="What Antar detected on the machine running the API. Remote AMD hosts are declared in configuration, not probed."
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
      <QueryView query={system}>{(data) => <Profile profile={data} />}</QueryView>
    </>
  );
}
