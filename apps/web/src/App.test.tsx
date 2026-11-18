import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { SETTINGS } from "./test/fixtures";

const RESPONSES: Record<string, unknown> = {
  "/health": { status: "ok", version: "0.1.0", time: "2026-01-01T00:00:00Z" },
  "/api/v1/backends": {
    backends: [
      { name: "lemonade", display_name: "Lemonade (local)", kind: "local", availability: "unavailable", detail: "Could not connect to Lemonade.", endpoint: "http://localhost:13305/v1", version: null, checked_at: "" },
      { name: "amd_cloud", display_name: "AMD cloud (ROCm)", kind: "cloud", availability: "not_configured", detail: "No AMD cloud profile configured.", endpoint: null, version: null, checked_at: "" },
    ],
  },
  "/api/v1/system": {
    hostname: "test-host", os: "Darwin", os_version: "27.0", architecture: "arm64", python_version: "3.13.0",
    cpu_model: "Test CPU", cpu_physical_cores: 8, cpu_logical_cores: 8,
    memory_total_bytes: 16_000_000_000, memory_available_bytes: 4_000_000_000,
    disk_total_bytes: 500_000_000_000, disk_free_bytes: 100_000_000_000, accelerators: [], runtimes: [],
  },
  "/api/v1/models": { models: [], sources: [] },
  "/api/v1/capabilities": { modalities: [], techniques: [], backends: [] },
  "/api/v1/experiments": { experiments: [] },
  "/api/v1/settings": SETTINGS,
};

function renderApp(path: string, fetchImpl: typeof fetch) {
  vi.stubGlobal("fetch", fetchImpl);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const apiUp: typeof fetch = async (input) => {
  const path = String(input);
  return path in RESPONSES
    ? new Response(JSON.stringify(RESPONSES[path]), { status: 200 })
    : new Response("{}", { status: 404 });
};
const apiDown: typeof fetch = async () => {
  throw new TypeError("Failed to fetch");
};

describe("App", () => {
  it("shows live backend status and hardware on the overview", async () => {
    renderApp("/", apiUp);

    expect(await screen.findByText("Could not connect to Lemonade.")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(await screen.findByText("Test CPU")).toBeInTheDocument();
    expect((await screen.findAllByText(/API connected, v0\.1\.0/)).length).toBeGreaterThan(0);
  });

  it("explains how to start the API when it cannot be reached", async () => {
    renderApp("/hardware", apiDown);

    const [alert] = await screen.findAllByRole("alert");
    expect(alert).toHaveTextContent("Can't reach the Antar API");
    expect(within(alert as HTMLElement).getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect((await screen.findAllByText("API unreachable")).length).toBeGreaterThan(0);
  });

  it("states that optimization cannot run and keeps the action disabled", async () => {
    renderApp("/optimization", apiUp);

    expect(await screen.findByRole("note")).toHaveTextContent("Not built yet");
    expect(await screen.findByRole("button", { name: "Run optimization" })).toBeDisabled();
  });

  it("shows an empty state instead of invented benchmark results", async () => {
    renderApp("/benchmarks", apiUp);

    expect(await screen.findByText("No experiments recorded")).toBeInTheDocument();
  });

  it("navigates to settings and shows the configured Lemonade endpoint", async () => {
    renderApp("/", apiUp);

    await userEvent.click(screen.getByRole("link", { name: "Settings" }));

    expect(await screen.findByText("http://localhost:13305/v1", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check connection" })).toBeInTheDocument();
  });
});
