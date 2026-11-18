import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type { ModelSpec } from "./lib/types";
import {
  CLOUD_MODEL,
  CLOUD_SETTINGS,
  CLOUD_UP,
  cloudStatus,
  comparisonReport,
  costEstimate,
  model,
  row,
  SETTINGS,
  WORKLOADS,
} from "./test/fixtures";

type Json = Record<string, unknown>;

interface Call {
  method: string;
  path: string;
  body: Json | null;
}

const LOCAL = model({});
const SOURCES = [
  { backend: "lemonade", display_name: "Lemonade (local)", availability: "available", model_count: 1, detail: "Connected." },
  { backend: "amd_cloud", display_name: "AMD cloud", availability: "available", model_count: 1, detail: "Connected." },
];
const NO_GPU = { ssh_configured: false, interval_seconds: null, sample: null, reason: "No SSH host is configured (amd_cloud in the configuration)." };

function setup(path: string, routes: Record<string, unknown> = {}, models: ModelSpec[] = [LOCAL, CLOUD_MODEL]): Call[] {
  const calls: Call[] = [];
  const base: Record<string, unknown> = {
    "/health": { status: "ok", version: "0.1.0", time: "" },
    "/api/v1/settings": CLOUD_SETTINGS,
    "/api/v1/models": { models, sources: SOURCES },
    "/api/v1/models/downloads": { downloads: [] },
    "/api/v1/benchmarks/workloads": { workloads: WORKLOADS },
    "/api/v1/benchmarks": { benchmarks: [] },
    "/api/v1/benchmarks/active": { active: null },
    "/api/v1/capabilities": { modalities: [], techniques: [], backends: [] },
    "/api/v1/cloud/status": CLOUD_UP,
    "/api/v1/cloud/gpus": NO_GPU,
    "/api/v1/cloud/catalog": { models: [] },
    "/api/v1/cloud/cost": costEstimate(),
    "/api/v1/cloud/lemonade-provider": { name: "antaramd", lemonade_reachable: true, supported: true, provider: null, detail: null },
    "/api/v1/comparisons": { comparisons: [] },
    "/api/v1/comparisons/active": { active: null },
    ...routes,
  };
  vi.stubGlobal("fetch", async (input: RequestInfo, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (method !== "GET") {
      calls.push({ method, path: url, body: init?.body ? (JSON.parse(String(init.body)) as Json) : null });
      const reply = routes[`${method} ${url}`] ?? {};
      return new Response(JSON.stringify(reply), { status: method === "POST" && url.endsWith("/comparisons") ? 202 : 200 });
    }
    return url in base ? new Response(JSON.stringify(base[url]), { status: 200 }) : new Response("{}", { status: 404 });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return calls;
}

describe("AMD Cloud page", () => {
  it("says plainly when no endpoint is configured and connects to nothing", async () => {
    setup("/cloud", { "/api/v1/cloud/status": cloudStatus() });

    const status = await screen.findByRole("status");
    expect(within(status).getByText("Not configured")).toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
    expect(await screen.findByText("GPU readings need SSH access to the host")).toBeInTheDocument();
  });

  it("reports an unreachable endpoint with the server's own reason", async () => {
    const down = cloudStatus({
      endpoint_configured: true,
      base_url: "http://127.0.0.1:18000/v1",
      loopback: true,
      status: { ...CLOUD_UP.status, availability: "unavailable", version: null, detail: "Could not connect to the cloud endpoint. Is the SSH tunnel open and vLLM running?" },
    });
    setup("/cloud", { "/api/v1/cloud/status": down });

    const status = await screen.findByRole("status");
    expect(within(status).getByText("Unreachable")).toBeInTheDocument();
    expect(within(status).getByText(/Is the SSH tunnel open/)).toBeInTheDocument();
    expect(screen.queryByText("Served models")).not.toBeInTheDocument();
  });

  it("shows GPU readings the host did not report as unavailable, never as zero", async () => {
    const gpus = {
      ssh_configured: true,
      interval_seconds: 10,
      reason: null,
      sample: {
        collected_at: "2026-11-18T10:00:00Z",
        gpus: [{ index: 0, name: "AMD Instinct MI300X", memory_total_bytes: 206_158_430_208, memory_used_bytes: null, utilization_percent: null, temperature_celsius: null, power_watts: null }],
        driver_version: null,
        rocm_version: null,
        amd_smi_version: null,
        unavailable: [{ metric: "gpu0.power_watts", reason: "amd-smi did not report this value in the form Antar reads." }],
      },
    };
    setup("/cloud", { "/api/v1/cloud/gpus": gpus });

    expect(within(await screen.findByRole("status")).getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText(CLOUD_MODEL.id)).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: /GPU readings/ });
    const cells = within(table).getAllByRole("cell").map((cell) => cell.textContent);
    expect(cells.filter((text) => text === "Unavailable")).toHaveLength(4);
    expect(cells.some((text) => /^0(\s|$)/.test(text ?? ""))).toBe(false);
    expect(screen.getByText(/Device-level, whole GPU/)).toBeInTheDocument();
    expect(screen.getByText("gpu0.power_watts")).toBeInTheDocument();
  });

  it("puts the server's cost warnings in front of the operator", async () => {
    const running = costEstimate({
      hourly_price_usd: 4,
      credit_balance_usd: 50,
      instance_started_at: "2026-11-18T10:00:00Z",
      running: true,
      warnings: [
        "Estimated spending has passed 80% of the credit.",
        "The instance is recorded as running. It bills until you stop it with your provider.",
      ],
    });
    setup("/cloud", { "/api/v1/cloud/cost": running });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("passed 80% of the credit");
    expect(alert).toHaveTextContent("bills until you stop it");
  });
});

describe("Comparison Lab", () => {
  it("sends nothing until the paid cloud time is explicitly confirmed", async () => {
    const calls = setup("/compare", { "/api/v1/cloud/cost": costEstimate({ hourly_price_usd: 3.5 }) });

    await userEvent.click(await screen.findByRole("button", { name: "Start comparison…" }));
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText("This uses paid cloud time")).toBeInTheDocument();
    expect(dialog).toHaveTextContent("$3.50 per hour");
    expect(calls).toEqual([]);

    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm and use cloud time" }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toMatchObject({
      method: "POST",
      path: "/api/v1/comparisons",
      body: {
        confirm_cloud_usage: true,
        config: {
          local: { backend: "lemonade", model: { id: LOCAL.id } },
          cloud: { backend: "amd_cloud", model: { id: CLOUD_MODEL.id } },
          workloads: ["qa_exact"],
          allow_code_execution: false,
        },
      },
    });
  });

  it("cancelling the confirmation sends nothing", async () => {
    const calls = setup("/compare");

    await userEvent.click(await screen.findByRole("button", { name: "Start comparison…" }));
    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(calls).toEqual([]);
  });

  it("shows the hardware caveat and leaves missing values unavailable in a report", async () => {
    const report = comparisonReport({
      rows: [
        row({ metric: "latency_ms_median", label: "End-to-end latency, median", local: 812, cloud: 1430 }),
        row({ metric: "tokens_per_second_median", label: "Tokens per second, backend-reported, median", unit: "tok/s", scope: "model", measured_by: "backend", local: 104.6, cloud: null }),
      ],
    });
    setup("/compare?report=cmp-1", { "/api/v1/comparisons/cmp-1": report });

    expect(await screen.findByText("Not a hardware-normalized comparison")).toBeInTheDocument();
    const backendRow = (await screen.findByText("Tokens per second, backend-reported, median")).closest("tr") as HTMLElement;
    expect(within(backendRow).getByText("Unavailable")).toBeInTheDocument();
    expect(within(backendRow).getByText("backend")).toBeInTheDocument();
    const latencyRow = screen.getByText("End-to-end latency, median", { selector: "th, td" }).closest("tr") as HTMLElement;
    expect(within(latencyRow).getByText("Antar API")).toBeInTheDocument();
  });
});

describe("Benchmarks with a cloud model", () => {
  it("asks for confirmation and sends confirm_cloud_usage only after it", async () => {
    const calls = setup("/benchmarks", {}, [CLOUD_MODEL]);

    await userEvent.click(await screen.findByRole("button", { name: "Start benchmark…" }));
    expect(calls).toEqual([]);
    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Confirm and use cloud time" }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]?.body).toMatchObject({ backend: "amd_cloud", confirm_cloud_usage: true, load_policy: "keep" });
  });

  it("never sends the cloud confirmation for a local model", async () => {
    const calls = setup("/benchmarks", {}, [LOCAL]);

    await userEvent.click(await screen.findByRole("button", { name: "Start benchmark" }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]?.body).not.toHaveProperty("confirm_cloud_usage");
  });
});

describe("Model Explorer", () => {
  it("filters to cloud models from the URL and offers no load or download for them", async () => {
    setup("/models?location=cloud");

    // The id and the checkpoint are the same repository name here, so it appears twice.
    const [cell] = await screen.findAllByText(CLOUD_MODEL.id);
    const row = cell?.closest("tr") as HTMLElement;
    expect(screen.queryByText(LOCAL.id)).not.toBeInTheDocument();
    expect(within(row).getByText("Cloud")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: /Download|Load|Unload/ })).not.toBeInTheDocument();
  });
});

describe("Lemonade cloud provider in Settings", () => {
  it("registers only after a confirmation that says Lemonade receives the key", async () => {
    const calls = setup("/settings");

    await userEvent.click(await screen.findByRole("button", { name: "Register…" }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("hands Lemonade the cloud endpoint's API key");
    expect(calls).toEqual([]);
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm and register" }));

    await waitFor(() => expect(calls).toEqual([{ method: "POST", path: "/api/v1/cloud/lemonade-provider", body: { confirm: true } }]));
  });

  it("reports an older Lemonade without cloud routing instead of assuming it", async () => {
    setup("/settings", {
      "/api/v1/cloud/lemonade-provider": { name: "antaramd", lemonade_reachable: true, supported: false, provider: null, detail: "This Lemonade version does not report cloud provider support." },
    });

    expect(await screen.findByText("Not supported by this Lemonade")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Register…" })).toBeDisabled();
  });

  it("shows Lemonade's own warnings for a registered provider verbatim", async () => {
    const provider = {
      name: "antaramd",
      base_url: "http://127.0.0.1:18000/v1",
      env_var_set: false,
      runtime_key_set: true,
      models_discovered: 1,
      allow_insecure_http: true,
      warnings: ["Base URL uses http://; traffic to this provider is not encrypted."],
    };
    setup("/settings", { "/api/v1/cloud/lemonade-provider": { name: "antaramd", lemonade_reachable: true, supported: true, provider, detail: null } });

    expect(await screen.findByText("Registered")).toBeInTheDocument();
    expect(screen.getByText("Base URL uses http://; traffic to this provider is not encrypted.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
  });

  it("cannot register when no cloud endpoint is configured", async () => {
    setup("/settings", { "/api/v1/settings": SETTINGS });

    expect(await screen.findByRole("button", { name: "Register…" })).toBeDisabled();
    expect(screen.getByText(/no cloud endpoint is configured/)).toBeInTheDocument();
  });
});
