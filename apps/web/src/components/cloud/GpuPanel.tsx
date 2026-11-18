import { useCloudGpus } from "../../lib/api";
import { bytesOrUnavailable, readingOrUnavailable } from "../../lib/cloud";
import { formatDateTime } from "../../lib/format";
import type { GpuSample, GpuTelemetry } from "../../lib/types";
import { Fact, Panel, QueryView, Value } from "../ui";

const DEVICE_LEVEL = "Device-level, whole GPU — not per model or per request.";

function GpuTable({ sample }: { sample: GpuSample }) {
  if (sample.gpus.length === 0) {
    return <p className="text-sm text-muted">The host answered, but reported no GPUs.</p>;
  }
  return (
    <div className="relative overflow-x-auto">
      <table className="w-full min-w-[40rem] border-separate border-spacing-0 text-sm">
        <caption className="sr-only">GPU readings from amd-smi on the AMD host</caption>
        <thead className="text-left text-muted">
          <tr>
            <th scope="col" className="pb-2 font-normal">GPU</th>
            {["Memory used", "Memory total", "Utilization", "Temperature", "Power"].map((heading) => (
              <th key={heading} scope="col" className="pb-2 pl-4 text-right font-normal">
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {sample.gpus.map((gpu) => (
            <tr key={gpu.index}>
              <th scope="row" className="border-t border-line py-2 pr-4 text-left font-normal">
                <span className="text-muted">{gpu.index}</span>{" "}
                {gpu.name ?? <span className="text-faint">Name unavailable</span>}
              </th>
              {[
                bytesOrUnavailable(gpu.memory_used_bytes),
                bytesOrUnavailable(gpu.memory_total_bytes),
                readingOrUnavailable(gpu.utilization_percent, "%"),
                readingOrUnavailable(gpu.temperature_celsius, "°C"),
                readingOrUnavailable(gpu.power_watts, "W"),
              ].map((value, column) => (
                <td key={column} className="border-t border-line py-2 pl-4 text-right whitespace-nowrap">
                  <Value>{value}</Value>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Readings({ telemetry }: { telemetry: GpuTelemetry }) {
  if (!telemetry.ssh_configured) {
    return (
      <div className="text-sm">
        <p className="font-medium">GPU readings need SSH access to the host</p>
        <p className="mt-1 max-w-[70ch] text-muted">
          {telemetry.reason} Antar reads GPUs by running <code className="font-mono">amd-smi</code>{" "}
          over SSH; the model endpoint alone does not report them. Add an{" "}
          <code className="font-mono">amd_cloud</code> profile with the SSH host to your config file,
          then restart the API.
        </p>
        <pre className="mt-3 overflow-x-auto rounded-md border border-line bg-ground px-3 py-2 font-mono text-xs text-muted">
          cp configs/antar.example.yaml configs/antar.yaml
        </pre>
      </div>
    );
  }
  const sample = telemetry.sample;
  if (!sample) {
    return (
      <p className="text-sm text-muted">
        No GPU reading is available. {telemetry.reason ?? "The host returned nothing to show."}
      </p>
    );
  }
  return (
    <div className="space-y-5">
      <GpuTable sample={sample} />
      <dl className="grid gap-x-10 sm:grid-cols-2">
        <Fact term="Driver">
          <Value>{sample.driver_version ?? "Unavailable"}</Value>
        </Fact>
        <Fact term="ROCm">
          <Value>{sample.rocm_version ?? "Unavailable"}</Value>
        </Fact>
        <Fact term="amd-smi">
          <Value>{sample.amd_smi_version ?? "Unavailable"}</Value>
        </Fact>
        <Fact term="Sampled">
          {formatDateTime(sample.collected_at)}
          {telemetry.interval_seconds !== null && (
            <span className="block text-2xs text-faint">At most every {telemetry.interval_seconds} s</span>
          )}
        </Fact>
      </dl>
      {sample.unavailable.length > 0 && (
        <div>
          <h3 className="text-sm font-medium">Not reported ({sample.unavailable.length})</h3>
          <ul className="mt-2 space-y-1 text-sm text-muted">
            {sample.unavailable.map((item) => (
              <li key={item.metric}>
                <span className="font-mono text-xs text-ink">{item.metric}</span>: {item.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function GpuPanel() {
  const gpus = useCloudGpus();
  return (
    <Panel title="GPUs" aside={<span className="text-xs text-faint">Measured by amd-smi on the host</span>}>
      <p className="mb-4 text-xs text-muted">{DEVICE_LEVEL}</p>
      <QueryView query={gpus}>{(telemetry) => <Readings telemetry={telemetry} />}</QueryView>
    </Panel>
  );
}
