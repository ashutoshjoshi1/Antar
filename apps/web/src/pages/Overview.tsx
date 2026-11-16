import { Link } from "react-router";

import { CapabilityMatrix } from "../components/CapabilityMatrix";
import { CloudLocalSpan } from "../components/CloudLocalSpan";
import { Fact, PageHeader, Panel, QueryView } from "../components/ui";
import { useBackends, useCapabilities, useModels, useSystem } from "../lib/api";
import { formatBytes, titleCase } from "../lib/format";
import { MODALITIES } from "../lib/types";
import type { ModelSpec } from "../lib/types";

function ModalityCounts({ models }: { models: ModelSpec[] }) {
  const real = models.filter((model) => !model.simulated);
  const largest = Math.max(
    1,
    ...MODALITIES.map((modality) => real.filter((m) => m.modalities.includes(modality)).length),
  );
  return (
    <ul className="space-y-2.5">
      {MODALITIES.map((modality) => {
        const count = real.filter((model) => model.modalities.includes(modality)).length;
        return (
          <li key={modality} className="grid grid-cols-[4.5rem_1fr_2rem] items-center gap-3 text-sm">
            <Link to={`/models?modality=${modality}`} className="hover:text-local">
              {titleCase(modality)}
            </Link>
            <span className="h-2 overflow-hidden rounded-full bg-raised">
              <span
                className="block h-full origin-left rounded-full bg-local/80"
                style={{ transform: `scaleX(${count / largest})` }}
              />
            </span>
            <span className="tabular text-right text-muted">{count}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function Overview() {
  const backends = useBackends();
  const system = useSystem();
  const models = useModels();
  const capabilities = useCapabilities();

  return (
    <>
      <PageHeader
        title="Overview"
        summary="Live status of this machine, the backends Antar can reach, and how much of the optimization pipeline exists."
      />

      <QueryView query={backends}>{(data) => <CloudLocalSpan backends={data} />}</QueryView>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <Panel title="What each backend can do" className="lg:col-span-3">
          <QueryView query={capabilities}>
            {(data) => <CapabilityMatrix backends={data.backends} />}
          </QueryView>
        </Panel>

        <div className="space-y-6 lg:col-span-2">
          <Panel title="This machine" aside={<Link to="/hardware" className="text-xs text-muted hover:text-ink">Details</Link>}>
            <QueryView query={system}>
              {(data) => (
                <dl>
                  <Fact term="Processor">{data.cpu_model}</Fact>
                  <Fact term="Memory">{formatBytes(data.memory_total_bytes)}</Fact>
                  <Fact term="Accelerator">
                    {data.accelerators.map((a) => a.name).join(", ") || "None detected"}
                  </Fact>
                  <Fact term="System">
                    {data.os} {data.os_version}, {data.architecture}
                  </Fact>
                </dl>
              )}
            </QueryView>
          </Panel>

          <Panel title="Discovered models by modality">
            <QueryView query={models}>
              {(data) => (
                <>
                  <ModalityCounts models={data.models} />
                  <p className="mt-4 text-xs text-faint">
                    Catalog entries reported by reachable backends, excluding mock models. A model
                    can count toward more than one modality.
                  </p>
                </>
              )}
            </QueryView>
          </Panel>
        </div>
      </div>
    </>
  );
}
