import { NotBuiltYet, PageHeader, Panel, QueryView, StatusPill, Tag } from "../components/ui";
import { useBackends } from "../lib/api";

/** Shape of antar/deployment/manifest.py, with placeholder values. */
const MANIFEST_FORMAT = `name: <deployment name>
model:
  id: <model id>
  revision: <pinned revision>
modality: text
task: chat
backend: lemonade
runtime_options: {}
routing:
  preference: local_first   # local_only | local_first | cloud_first | cloud_only
  local_backend: lemonade
  cloud_backend: amd_cloud
  max_local_latency_ms: <limit>
  max_local_memory_gb: <limit>
experiment_id: <experiment that justifies this configuration>
artifacts:
  - kind: weights
    path: <path>
    sha256: <digest>
    size_bytes: <bytes>`;

export function Deployments() {
  const backends = useBackends();
  return (
    <>
      <PageHeader
        title="Deployments"
        summary="A deployment pins a model, a backend, and a routing rule for choosing between this device and the cloud."
      />
      <NotBuiltYet>
        Antar cannot deploy a model or route requests yet, so there are no deployments to list. The
        targets below show their current status; the manifest shows the format a deployment will be exported in.
      </NotBuiltYet>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Deployment targets">
          <QueryView query={backends}>
            {(data) => (
              <ul className="divide-y divide-line">
                {data
                  .filter((backend) => backend.kind !== "mock")
                  .map((backend) => (
                    <li key={backend.name} className="py-3 first:pt-0 last:pb-0">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium">
                          {backend.display_name}{" "}
                          <span className={backend.kind === "cloud" ? "text-cloud" : "text-local"}>
                            {backend.kind}
                          </span>
                        </span>
                        <StatusPill availability={backend.availability} />
                      </div>
                      <p className="mt-1 text-sm text-muted">{backend.detail}</p>
                    </li>
                  ))}
              </ul>
            )}
          </QueryView>
        </Panel>

        <Panel title="Manifest format" aside={<Tag>Format only, no real deployment</Tag>}>
          <pre className="overflow-x-auto font-mono text-xs leading-relaxed text-muted">{MANIFEST_FORMAT}</pre>
        </Panel>
      </div>
    </>
  );
}
