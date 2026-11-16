import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { requestCount } from "./components/benchmarks/BenchmarkForm";
import { usableModels } from "./components/chat/ChatWorkspace";
import type { ModelSpec, Workload } from "./lib/types";

function model(overrides: Partial<ModelSpec>): ModelSpec {
  return {
    id: "Qwen3-1.7B-GGUF",
    name: "Qwen3-1.7B-GGUF",
    backend: "lemonade",
    modalities: ["text"],
    tasks: ["chat"],
    revision: null,
    checkpoint: "unsloth/Qwen3-1.7B-GGUF:Q4_0",
    runtime: "llamacpp",
    size_bytes: 984_000_000,
    license: null,
    downloaded: true,
    loaded: true,
    quantization: "Q4_0",
    context_length: 40960,
    labels: ["chat", "reasoning"],
    simulated: false,
    ...overrides,
  };
}

const TEXT = model({});
const VLM_CATALOG = model({
  id: "Qwen3-VL-4B-Instruct-GGUF",
  modalities: ["text", "vision"],
  tasks: ["chat", "image_understanding"],
  downloaded: false,
  loaded: false,
  size_bytes: 3_330_000_000,
  labels: ["chat", "vision"],
});
const MOCK = model({ id: "mock/echo-small", backend: "mock", simulated: true });
const SOURCE_UP = { backend: "lemonade", display_name: "Lemonade (local)", availability: "available", model_count: 2, detail: "Connected." };

const WORKLOADS: Workload[] = [
  { id: "general_qa", name: "General question answering", description: "Short questions.", modality: "text", version: "1", check: null, prompts: [1, 2, 3, 4].map((n) => ({ id: `p${n}`, text: "?", image: null })) },
  { id: "vision_basic", name: "Basic image understanding", description: "Images.", modality: "vision", version: "1", check: null, prompts: [1, 2, 3].map((n) => ({ id: `v${n}`, text: "?", image: "x.png" })) },
];

const RESULT = {
  backend: "lemonade", model: TEXT.id, content: "Hello there", reasoning: "Greet back.", finish_reason: "stop", simulated: false,
  metrics: { latency_ms: 197, first_chunk_ms: 44, prompt_tokens: 19, completion_tokens: 17, cached_prompt_tokens: 3, prompt_processing_ms: 24, generation_ms: 153, tokens_per_second: 104.6 },
};

type Json = Record<string, unknown>;

interface Calls {
  posts: { path: string; body: Json }[];
}

function setup(path: string, routes: Record<string, unknown>, streamBody?: string): Calls {
  const calls: Calls = { posts: [] };
  const base: Record<string, unknown> = {
    "/health": { status: "ok", version: "0.1.0", time: "" },
    "/api/v1/settings": { inference: { max_image_bytes: 8 * 1024 * 1024, generation_timeout_seconds: 300 }, storage: {} },
    "/api/v1/models/downloads": { downloads: [] },
    "/api/v1/benchmarks/workloads": { workloads: WORKLOADS },
    "/api/v1/benchmarks": { benchmarks: [] },
    "/api/v1/benchmarks/active": { active: null },
    "/api/v1/capabilities": { modalities: [], techniques: [], backends: [] },
    "/api/v1/experiments": { experiments: [] },
    ...routes,
  };
  vi.stubGlobal("fetch", async (input: RequestInfo, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === "POST") {
      calls.posts.push({ path: url, body: JSON.parse(String(init.body)) as Json });
      if (url.endsWith("/chat/stream")) return new Response(streamBody ?? "", { status: 200 });
      if (url === "/api/v1/benchmarks") {
        return new Response(JSON.stringify({ active: { id: "bench-1", name: "run", model: TEXT.id, status: "running", completed_requests: 2, total_requests: 13, current: "General question answering: p3 (measured)", started_at: "", failure: null } }), { status: 202 });
      }
      return new Response("{}", { status: 200 });
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

const sse = (...events: unknown[]) => events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
const inventory = (...models: ModelSpec[]) => ({ "/api/v1/models": { models, sources: [SOURCE_UP] } });

describe("usableModels", () => {
  it("offers only real, downloaded chat models, and only vision models in vision mode", () => {
    const vlm = { ...VLM_CATALOG, downloaded: true };
    const all = [MOCK, VLM_CATALOG, TEXT, vlm];

    expect(usableModels(all, "text").map((item) => item.id)).toEqual([TEXT.id, vlm.id]);
    expect(usableModels(all, "vision").map((item) => item.id)).toEqual([vlm.id]);
    expect(usableModels([MOCK, VLM_CATALOG], "text")).toEqual([]);
  });
});

describe("Playground", () => {
  it("streams a reply, shows reasoning separately, and reports measured statistics", async () => {
    const stream = sse(
      { type: "delta", content: "", reasoning: "Greet back." },
      { type: "delta", content: "Hello", reasoning: "" },
      { type: "delta", content: " there", reasoning: "" },
      { type: "done", result: RESULT },
    );
    const calls = setup("/playground", inventory(TEXT), stream);

    await userEvent.type(await screen.findByLabelText("Prompt"), "Say hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Hello there")).toBeInTheDocument();
    expect(screen.getByText("Greet back.")).toBeInTheDocument();
    expect(await screen.findByText("104.6 tokens/s")).toBeInTheDocument();
    expect(screen.getByText("19 (3 cached)")).toBeInTheDocument();
    expect(screen.getByText("44 ms")).toBeInTheDocument();

    const [sent] = calls.posts;
    expect(sent?.body).toMatchObject({
      backend: "lemonade",
      model: TEXT.id,
      messages: [{ role: "user", content: "Say hello" }],
      settings: { max_tokens: 512, enable_thinking: true },
    });
  });

  it("sends the conversation so far with a follow-up question", async () => {
    const calls = setup("/playground", inventory(TEXT), sse({ type: "done", result: RESULT }));

    await userEvent.type(await screen.findByLabelText("Prompt"), "First{Enter}");
    await screen.findByText("Hello there");
    await userEvent.type(screen.getByLabelText("Prompt"), "Second{Enter}");

    await waitFor(() => expect(calls.posts).toHaveLength(2));
    expect(calls.posts[1]?.body.messages).toEqual([
      { role: "user", content: "First" },
      { role: "assistant", content: "Hello there" },
      { role: "user", content: "Second" },
    ]);
  });

  it("shows the server's error and keeps the question, without inventing a reply", async () => {
    setup("/playground", inventory(TEXT), sse({ type: "error", message: "Lemonade error (HTTP 500): out of memory", kind: "BackendRequestError" }));

    await userEvent.type(await screen.findByLabelText("Prompt"), "Hi{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent("out of memory");
    expect(screen.getByText("Hi")).toBeInTheDocument();
    expect(screen.queryByText("Waiting for the first token…")).not.toBeInTheDocument();
    expect(document.querySelectorAll("ol[aria-live] > li")).toHaveLength(1);
    expect(screen.getByText("Measurements appear here after a response.")).toBeInTheDocument();
  });

  it("explains an empty answer when reasoning used up the output limit", async () => {
    const exhausted = { ...RESULT, content: "", reasoning: "Let me think about this at length", finish_reason: "length" };
    const calls = setup("/playground", inventory({ ...TEXT, labels: ["chat"] }), sse({ type: "done", result: exhausted }));

    await userEvent.type(await screen.findByLabelText("Prompt"), "Hi{Enter}");

    expect(await screen.findByText(/used its whole output limit on reasoning/)).toBeInTheDocument();
    // The option is sent even though this model is not labelled as a reasoning model.
    expect(calls.posts[0]?.body.settings).toMatchObject({ enable_thinking: true });
    await userEvent.click(screen.getByLabelText("Let the model reason first"));
    await userEvent.type(screen.getByLabelText("Prompt"), "Again{Enter}");
    await waitFor(() => expect(calls.posts).toHaveLength(2));
    expect(calls.posts[1]?.body).toMatchObject({ settings: { enable_thinking: false }, messages: [{ role: "user", content: "Again" }] });
  });

  it("does not send an empty prompt", async () => {
    const calls = setup("/playground", inventory(TEXT));

    expect(await screen.findByRole("button", { name: "Send" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Prompt"), "   {Enter}");

    expect(calls.posts).toEqual([]);
  });

  it("explains when Lemonade is down instead of offering the mock", async () => {
    setup("/playground", { "/api/v1/models": { models: [MOCK], sources: [{ ...SOURCE_UP, availability: "unavailable", detail: "Could not connect to Lemonade at http://localhost:13305/v1/health." }] } });

    expect(await screen.findByText("Lemonade is not reachable")).toBeInTheDocument();
    expect(screen.getByText(/Could not connect to Lemonade/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Prompt")).not.toBeInTheDocument();
  });
});

describe("Vision", () => {
  it("says no vision model is downloaded and lists the smallest ones with sizes", async () => {
    setup("/vision", inventory(TEXT, VLM_CATALOG));

    expect(await screen.findByText("No vision model is downloaded")).toBeInTheDocument();
    expect(screen.getByText("Qwen3-VL-4B-Instruct-GGUF")).toBeInTheDocument();
    expect(screen.getByText("3.3 GB")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the Models page" })).toHaveAttribute("href", "/models?modality=vision");
  });

  it("requires an image before the first question and rejects unsupported files", async () => {
    const calls = setup("/vision", inventory({ ...VLM_CATALOG, downloaded: true }));

    await userEvent.type(await screen.findByLabelText("Question about the image"), "What is this?");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

    const picker = screen.getByLabelText("Choose an image");
    await userEvent.upload(picker, new File(["GIF89a"], "anim.gif", { type: "image/gif" }), { applyAccept: false });
    expect(await screen.findByText("Use a PNG, JPEG, or WebP image.")).toBeInTheDocument();
    expect(calls.posts).toEqual([]);
  });

  it("sends the uploaded image with the first question only", async () => {
    const calls = setup("/vision", inventory({ ...VLM_CATALOG, downloaded: true }), sse({ type: "done", result: RESULT }));

    await userEvent.upload(await screen.findByLabelText("Choose an image"), new File([new Uint8Array([137, 80, 78, 71])], "shot.png", { type: "image/png" }));
    await screen.findAllByAltText("Selected for analysis");
    await userEvent.type(screen.getByLabelText("Question about the image"), "Describe this image.{Enter}");
    await screen.findByText("Hello there");
    await userEvent.type(screen.getByLabelText("Question about the image"), "And the colors?{Enter}");

    await waitFor(() => expect(calls.posts).toHaveLength(2));
    const messages = calls.posts[1]?.body.messages as Json[];
    expect(messages[0]).toMatchObject({ images: [{ media_type: "image/png", data_base64: "iVBORw==" }] });
    expect(messages[2]).toEqual({ role: "user", content: "And the colors?" });
  });
});

describe("Models", () => {
  it("asks for confirmation with the size before starting a download", async () => {
    const calls = setup("/models", inventory(TEXT, VLM_CATALOG));

    const row = (await screen.findByText("Qwen3-VL-4B-Instruct-GGUF")).closest("tr") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Download…" }));
    expect(calls.posts).toEqual([]);

    await userEvent.click(within(row).getByRole("button", { name: "Download 3.3 GB" }));

    expect(calls.posts).toEqual([
      { path: "/api/v1/models/download", body: { backend: "lemonade", model: "Qwen3-VL-4B-Instruct-GGUF", confirm: true } },
    ]);
  });

  it("offers unload for a loaded model and shows its quantization", async () => {
    const calls = setup("/models", inventory(TEXT));

    const row = (await screen.findByText(TEXT.id)).closest("tr") as HTMLElement;
    expect(within(row).getByText("Loaded")).toBeInTheDocument();
    expect(within(row).getByText("Q4_0")).toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: "Unload" }));

    expect(calls.posts[0]).toEqual({ path: "/api/v1/models/unload", body: { backend: "lemonade", model: TEXT.id } });
  });
});

describe("Benchmarks", () => {
  it("counts requests the way the runner does", () => {
    expect(requestCount(WORKLOADS, ["general_qa"], 1, 3, "keep")).toBe(13);
    expect(requestCount(WORKLOADS, ["general_qa", "vision_basic"], 0, 2, "reload")).toBe(15);
    expect(requestCount(WORKLOADS, [], 1, 3, "reload")).toBe(0);
  });

  it("starts a benchmark with comparable defaults and shows real progress", async () => {
    const calls = setup("/benchmarks", inventory(TEXT));

    expect(await screen.findByText(/13 requests, one at a time/)).toBeInTheDocument();
    expect(screen.getByText("Needs a vision model")).toBeInTheDocument();
    expect(screen.getByText(/No benchmark has been run yet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start benchmark" }));

    expect(calls.posts[0]?.body).toMatchObject({
      model: { id: TEXT.id },
      backend: "lemonade",
      workloads: ["general_qa"],
      warmup_runs: 1,
      measured_runs: 3,
      temperature: 0,
      seed: 42,
      enable_thinking: false,
      load_policy: "keep",
    });
    expect(await screen.findByText(/2 of 13 requests/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Benchmark running" })).toBeDisabled();
  });
});
