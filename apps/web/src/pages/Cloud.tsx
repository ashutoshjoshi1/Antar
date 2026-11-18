import { ConnectionPanel } from "../components/cloud/ConnectionPanel";
import { CostPanel } from "../components/cloud/CostPanel";
import { FeasibilityPanel } from "../components/cloud/FeasibilityPanel";
import { GpuPanel } from "../components/cloud/GpuPanel";
import { PreflightPanel } from "../components/cloud/PreflightPanel";
import { LocationBadge, PageHeader, QueryView } from "../components/ui";
import { useCloudStatus } from "../lib/api";

export function Cloud() {
  const status = useCloudStatus();
  return (
    <>
      <PageHeader
        title="AMD Cloud"
        summary="The AMD GPU host Antar can send requests to: whether it answers, what it serves, what its GPUs report, and what it is costing. Antar never starts, stops, or resizes a machine."
        actions={<LocationBadge location="cloud" detail="vLLM on ROCm" />}
      />
      <div className="space-y-6">
        <QueryView query={status}>
          {(data) => (
            <>
              <ConnectionPanel
                status={data}
                checking={status.isFetching}
                onCheck={() => void status.refetch()}
              />
              <GpuPanel />
              <PreflightPanel sshConfigured={data.ssh_configured} />
            </>
          )}
        </QueryView>
        <FeasibilityPanel />
        <CostPanel />
      </div>
    </>
  );
}
