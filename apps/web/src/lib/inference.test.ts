import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import { comparisonIssues } from "./benchmarks";
import { splitEvents, streamChat } from "./chatStream";
import { formatCount, formatDuration, formatPercent } from "./format";
import { rejectReason } from "./image";
import type { BenchmarkReport, ChatBody, ChatResult } from "./types";
import { toApiMessages } from "./useChat";
import type { Turn } from "./useChat";

const RESULT: ChatResult = {
  backend: "lemonade",
  model: "m",
  content: "Hello",
  reasoning: null,
  finish_reason: "stop",
  simulated: false,
  metrics: {
    latency_ms: 200,
    first_chunk_ms: 40,
    prompt_tokens: 10,
    completion_tokens: 2,
    cached_prompt_tokens: null,
    prompt_processing_ms: 20,
    generation_ms: 150,
    tokens_per_second: 100,
  },
};
const BODY: ChatBody = { backend: "lemonade", model: "m", messages: [{ role: "user", content: "hi" }], settings: { max_tokens: 8 } };

const event = (value: unknown) => `data: ${JSON.stringify(value)}\n\n`;

/** A fetch whose body arrives in the given chunks, to exercise split events. */
function stubStream(chunks: string[], status = 200) {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
      controller.close();
    },
  });
  vi.stubGlobal("fetch", async () => new Response(body, { status }));
}

describe("splitEvents", () => {
  it("returns complete events and keeps an unfinished one for the next chunk", () => {
    const first = event({ type: "delta", content: "a", reasoning: "" });
    const partial = 'data: {"type":"del';

    expect(splitEvents(first + partial)).toEqual({
      events: [{ type: "delta", content: "a", reasoning: "" }],
      rest: partial,
    });
  });
});

describe("streamChat", () => {
  it("delivers deltas in order and resolves with the final result", async () => {
    const whole = event({ type: "delta", content: "Hel", reasoning: "why" }) + event({ type: "delta", content: "lo", reasoning: "" }) + event({ type: "done", result: RESULT });
    // Split mid-event to prove events are reassembled across network chunks.
    stubStream([whole.slice(0, 25), whole.slice(25, 90), whole.slice(90)]);
    const deltas: string[] = [];

    const result = await streamChat(BODY, {
      signal: new AbortController().signal,
      onDelta: (content, reasoning) => deltas.push(`${content}|${reasoning}`),
    });

    expect(deltas).toEqual(["Hel|why", "lo|"]);
    expect(result.metrics.tokens_per_second).toBe(100);
  });

  it("rejects with the server's message when generation fails mid-stream", async () => {
    stubStream([event({ type: "delta", content: "x", reasoning: "" }), event({ type: "error", message: "out of memory", kind: "BackendRequestError" })]);

    await expect(streamChat(BODY, { signal: new AbortController().signal, onDelta: () => {} })).rejects.toThrow("out of memory");
  });

  it("rejects when the stream ends without a result", async () => {
    stubStream([event({ type: "delta", content: "x", reasoning: "" })]);

    await expect(streamChat(BODY, { signal: new AbortController().signal, onDelta: () => {} })).rejects.toThrow(ApiError);
  });

  it("surfaces the API's explanation for a refused request", async () => {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ detail: "'m' is not downloaded." }), { status: 409 }));

    await expect(streamChat(BODY, { signal: new AbortController().signal, onDelta: () => {} })).rejects.toThrow("'m' is not downloaded.");
  });
});

describe("toApiMessages", () => {
  const turn = (id: number, role: Turn["role"], content: string, extra: Partial<Turn> = {}): Turn => ({ id, role, content, reasoning: "", ...extra });

  it("sends a completed conversation unchanged", () => {
    expect(toApiMessages([turn(1, "user", "Hi"), turn(2, "assistant", "Hello"), turn(3, "user", "More")])).toEqual([
      { role: "user", content: "Hi" },
      { role: "assistant", content: "Hello" },
      { role: "user", content: "More" },
    ]);
  });

  it("leaves out an exchange stopped before any text arrived", () => {
    const turns = [turn(1, "user", "Hi"), turn(2, "assistant", "", { stopped: true, reasoning: "thinking" }), turn(3, "user", "Again")];

    expect(toApiMessages(turns)).toEqual([{ role: "user", content: "Again" }]);
  });

  it("keeps a reply that was stopped partway", () => {
    const turns = [turn(1, "user", "Hi"), turn(2, "assistant", "Hel", { stopped: true }), turn(3, "user", "Go on")];

    expect(toApiMessages(turns).map((message) => message.content)).toEqual(["Hi", "Hel", "Go on"]);
  });

  it("does not resend a question whose request failed", () => {
    const turns = [turn(1, "user", "Hi", { failed: true }), turn(2, "user", "Retry")];

    expect(toApiMessages(turns)).toEqual([{ role: "user", content: "Retry" }]);
  });
});

describe("unavailable values", () => {
  it("are labelled, never shown as zero", () => {
    expect(formatDuration(null)).toBe("Unavailable");
    expect(formatCount(undefined)).toBe("Unavailable");
    expect(formatPercent(null)).toBe("Unavailable");
  });

  it("format real measurements", () => {
    expect(formatDuration(43.8)).toBe("44 ms");
    expect(formatDuration(1526)).toBe("1.53 s");
    expect(formatCount(103.34, "tokens/s")).toBe("103.3 tokens/s");
    expect(formatCount(153)).toBe("153");
    expect(formatPercent(0)).toBe("0%");
    expect(formatPercent(0.05)).toBe("5.0%");
  });
});

describe("rejectReason", () => {
  const LIMIT = 8 * 1024 * 1024;

  it("accepts PNG, JPEG and WebP within the limit", () => {
    for (const type of ["image/png", "image/jpeg", "image/webp"]) {
      expect(rejectReason({ type, size: 1000 }, LIMIT)).toBeNull();
    }
  });

  it("explains unsupported types and oversized files", () => {
    expect(rejectReason({ type: "image/gif", size: 10 }, LIMIT)).toBe("Use a PNG, JPEG, or WebP image.");
    expect(rejectReason({ type: "image/png", size: 9 * 1024 * 1024 }, LIMIT)).toBe("That image is 9.0 MB. The limit is 8 MB.");
  });
});

describe("comparisonIssues", () => {
  const report = (overrides: Partial<BenchmarkReport["config"]> = {}, extra: Partial<BenchmarkReport> = {}) =>
    ({
      status: "completed",
      simulated: false,
      workloads: [{ id: "general_qa", version: "1" }],
      hardware: { cpu_model: "Apple M3 Pro" },
      config: { max_tokens: 256, temperature: 0, seed: 42, enable_thinking: false, ...overrides },
      ...extra,
    }) as BenchmarkReport;

  it("finds nothing wrong with identical prompts and settings", () => {
    expect(comparisonIssues(report(), report())).toEqual([]);
  });

  it("names every difference that makes a comparison unfair", () => {
    const other = report({ max_tokens: 64, temperature: 0.7 }, { simulated: true, workloads: [{ id: "general_qa", version: "2" }] } as Partial<BenchmarkReport>);

    expect(comparisonIssues(report(), other)).toEqual([
      "Different workloads: general_qa@1 versus general_qa@2.",
      "Different max tokens: 256 versus 64.",
      "Different temperature: 0 versus 0.7.",
      "At least one report is simulated, not measured.",
    ]);
  });
});
