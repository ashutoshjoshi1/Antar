import { Fact, PageHeader, Panel, QueryView, StatusPill } from "../components/ui";
import { useBackends, useSettings } from "../lib/api";
import { titleCase } from "../lib/format";
import type { BackendStatus, SettingsView } from "../lib/types";

function Code({ children }: { children: string }) {
  return (
    <pre className="mt-3 overflow-x-auto rounded-md border border-line bg-ground px-3 py-2 font-mono text-xs text-muted">
      {children}
    </pre>
  );
}

function BackendCheck({ name, backends }: { name: string; backends: BackendStatus[] | undefined }) {
  const backend = backends?.find((candidate) => candidate.name === name);
  if (!backend) return null;
  return (
    <div className="mb-4 rounded-md border border-line bg-ground px-3 py-2.5">
      <StatusPill availability={backend.availability} />
      <p className="mt-1 text-sm text-muted">{backend.detail}</p>
    </div>
  );
}

function SettingsPanels({ settings }: { settings: SettingsView }) {
  const backends = useBackends();
  const cloud = settings.amd_cloud;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel
        title="Lemonade"
        aside={
          <button
            type="button"
            onClick={() => void backends.refetch()}
            className="rounded-md border border-line px-2.5 py-1 text-xs hover:border-muted active:bg-raised"
          >
            {backends.isFetching ? "Checking…" : "Check connection"}
          </button>
        }
      >
        <BackendCheck name="lemonade" backends={backends.data} />
        <dl>
          <Fact term="Endpoint">
            <span className="font-mono text-xs">{settings.lemonade.base_url}</span>
          </Fact>
          <Fact term="API key">{settings.lemonade.api_key_configured ? "Configured" : "Not set"}</Fact>
          <Fact term="Timeout">{settings.lemonade.timeout_seconds} s</Fact>
        </dl>
        <p className="mt-4 text-sm text-muted">
          To use a different server, set the endpoint before starting the API. Include the{" "}
          <code className="font-mono">/v1</code> prefix.
        </p>
        <Code>ANTAR_LEMONADE__BASE_URL=http://localhost:13305/v1</Code>
      </Panel>

      <Panel title="AMD cloud">
        <BackendCheck name="amd_cloud" backends={backends.data} />
        {cloud ? (
          <dl>
            <Fact term="Profile">{cloud.name}</Fact>
            <Fact term="Host">
              <span className="font-mono text-xs">
                {cloud.ssh_user}@{cloud.ssh_host}:{cloud.ssh_port}
              </span>
            </Fact>
            <Fact term="SSH key">{cloud.ssh_key_configured ? "Path configured" : "Not set"}</Fact>
            <Fact term="Working directory">
              <span className="font-mono text-xs">{cloud.remote_workdir}</span>
            </Fact>
            <Fact term="ROCm">{cloud.rocm_version ?? "Not declared"}</Fact>
            <Fact term="GPUs">
              {cloud.gpus.map((gpu) => `${gpu.count} × ${gpu.name}`).join(", ") || "Not declared"}
            </Fact>
          </dl>
        ) : (
          <p className="text-sm text-muted">
            Optional. Add an <code className="font-mono">amd_cloud</code> profile to your config file
            to describe a remote AMD GPU host. Antar validates the profile but never connects or
            starts paid resources on its own.
          </p>
        )}
        <Code>cp configs/antar.example.yaml configs/antar.yaml</Code>
      </Panel>

      <Panel title="Storage" className="lg:col-span-2">
        <dl className="grid gap-x-10 sm:grid-cols-2">
          {Object.entries(settings.storage).map(([key, path]) => (
            <Fact key={key} term={titleCase(key.replace("_dir", ""))}>
              <span className="font-mono text-xs">{path}</span>
            </Fact>
          ))}
          <Fact term="Config file">
            <span className="font-mono text-xs">{settings.config_file}</span>{" "}
            <span className="text-muted">{settings.config_file_found ? "(loaded)" : "(not found, using defaults)"}</span>
          </Fact>
          <Fact term="Mock backend">{settings.mock_backend_enabled ? "On" : "Off"}</Fact>
        </dl>
      </Panel>
    </div>
  );
}

export function Settings() {
  const settings = useSettings();
  return (
    <>
      <PageHeader
        title="Settings"
        summary="The configuration the API is running with. Settings are read from environment variables and a YAML file, and are changed there rather than here."
      />
      <QueryView query={settings}>{(data) => <SettingsPanels settings={data} />}</QueryView>
    </>
  );
}
