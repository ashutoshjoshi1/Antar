import type { BackendStatus } from "../lib/types";
import { StatusPill, Tag } from "./ui";

type StageState = "partial" | "planned";

interface Stage {
  name: string;
  state: StageState;
  note: string;
}

/** The optimization pipeline, in execution order. States describe this codebase today. */
const PIPELINE: readonly Stage[] = [
  { name: "Accept model and workload", state: "partial", note: "Typed job spec validates; no intake flow." },
  { name: "Identify hardware", state: "partial", note: "Local detection works; cloud is declared, not probed." },
  { name: "Measure baseline", state: "partial", note: "Performance benchmarks run; no quality evaluators." },
  { name: "Choose techniques", state: "partial", note: "Applicability matrix only." },
  { name: "Run experiments", state: "planned", note: "" },
  { name: "Benchmark candidates", state: "partial", note: "Same runner; no candidates are produced yet." },
  { name: "Compare results", state: "planned", note: "" },
  { name: "Select configuration", state: "planned", note: "" },
  { name: "Export artifacts", state: "planned", note: "Manifest and record formats defined." },
];

function Pole({ side, backends }: { side: "cloud" | "local"; backends: BackendStatus[] }) {
  const isCloud = side === "cloud";
  return (
    <div className={`rounded-lg border bg-ground/60 p-4 ${isCloud ? "border-cloud/40" : "border-local/40"}`}>
      <p className={`text-lg font-semibold ${isCloud ? "text-cloud" : "text-local"}`}>
        {isCloud ? "Cloud" : "Local"}
      </p>
      <p className="mt-0.5 text-sm text-muted">
        {isCloud ? "Remote AMD GPUs through ROCm" : "On-device inference through Lemonade"}
      </p>
      <ul className="mt-4 space-y-3">
        {backends.map((backend) => (
          <li key={backend.name}>
            <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
              <span className="text-sm font-medium">{backend.display_name}</span>
              <StatusPill availability={backend.availability} />
            </div>
            <p className="mt-1 text-xs text-muted">{backend.detail}</p>
            {backend.endpoint && (
              <p className="mt-1 font-mono text-xs break-all text-faint">{backend.endpoint}</p>
            )}
            {backend.version && <p className="text-xs text-faint">Version {backend.version}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CloudLocalSpan({ backends }: { backends: BackendStatus[] }) {
  const cloud = backends.filter((backend) => backend.kind === "cloud");
  const local = backends.filter((backend) => backend.kind === "local");
  const mock = backends.filter((backend) => backend.kind === "mock");

  return (
    <section
      aria-labelledby="span-heading"
      className="rounded-xl border border-line bg-surface p-5 sm:p-6"
    >
      <h2 id="span-heading" className="text-sm font-medium">
        From cloud to local
      </h2>
      <p className="mt-1 max-w-[70ch] text-sm text-muted">
        Antar optimizes a model on cloud GPUs until it fits the device in front of you. These nine
        stages cross that distance; most are not built yet.
      </p>

      <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(0,17rem)_1fr_minmax(0,17rem)]">
        <Pole side="cloud" backends={cloud} />

        <div className="min-w-0">
          <div
            aria-hidden
            className="relative mx-1 mb-5 hidden h-px bg-gradient-to-r from-cloud via-line to-local xl:block"
          >
            <div className="absolute inset-x-0 -top-1 motion-safe:animate-[span-signal_5s_var(--ease-out-expo)_infinite]">
              <span className="block size-2 rounded-full bg-ink" />
            </div>
          </div>
          <ol className="grid gap-x-6 gap-y-3 sm:grid-cols-2 2xl:grid-cols-3">
            {PIPELINE.map((stage, index) => (
              <li key={stage.name} className="flex gap-3 text-sm">
                <span className="tabular w-5 shrink-0 pt-px text-right font-mono text-xs text-faint">
                  {index + 1}
                </span>
                <span className="min-w-0">
                  <span className={stage.state === "planned" ? "text-muted" : "text-ink"}>
                    {stage.name}
                  </span>{" "}
                  <Tag tone={stage.state === "partial" ? "warn" : "plain"}>
                    {stage.state === "partial" ? "Partial" : "Planned"}
                  </Tag>
                  {stage.note && <span className="mt-0.5 block text-xs text-faint">{stage.note}</span>}
                </span>
              </li>
            ))}
          </ol>
        </div>

        <Pole side="local" backends={local} />
      </div>

      {mock.length > 0 && (
        <p className="mt-5 border-t border-line pt-4 text-xs text-muted">
          The mock backend is on for development. Anything it produces is simulated and labelled as
          such.
        </p>
      )}
    </section>
  );
}
