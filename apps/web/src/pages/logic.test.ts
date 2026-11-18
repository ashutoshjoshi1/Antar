import { describe, expect, it } from "vitest";

import { summarize } from "../components/CapabilityMatrix";
import { filterModels, NO_FILTERS } from "../lib/models";
import type { BackendCapabilities } from "../lib/types";
import { model } from "../test/fixtures";
import { buildJobPreview } from "./Optimization";

const MODELS = [
  model({ id: "Qwen3-GGUF", labels: ["reasoning"], downloaded: true }),
  model({ id: "Gemma-Vision", modalities: ["text", "vision"], labels: [], downloaded: false, loaded: false, state: "discovered" }),
  model({ id: "Whisper-Tiny", modalities: ["speech"], labels: ["transcription"], downloaded: false, loaded: false, state: "discovered" }),
];
const NO_FILTER = NO_FILTERS;

describe("filterModels", () => {
  it("returns everything with no filters", () => {
    expect(filterModels(MODELS, NO_FILTER)).toHaveLength(3);
  });

  it("filters by modality, including multimodal models", () => {
    const ids = filterModels(MODELS, { ...NO_FILTER, modality: "vision" }).map((m) => m.id);
    expect(ids).toEqual(["Gemma-Vision"]);
  });

  it("matches search against id and labels, ignoring case", () => {
    expect(filterModels(MODELS, { ...NO_FILTER, search: "QWEN" })).toHaveLength(1);
    expect(filterModels(MODELS, { ...NO_FILTER, search: "transcr" })).toHaveLength(1);
  });

  it("keeps only models known to be downloaded", () => {
    const ids = filterModels(MODELS, { ...NO_FILTER, downloadedOnly: true }).map((m) => m.id);
    expect(ids).toEqual(["Qwen3-GGUF"]);
  });
});

describe("buildJobPreview", () => {
  const draft = { modelKey: "", techniques: ["quantization"], maxMemoryGb: "8", maxQualityDrop: "5" };

  it("builds a job with constraints converted to API units", () => {
    const preview = buildJobPreview(model({ id: "Org/My Model" }), draft);

    expect(preview).toMatchObject({
      name: "optimize-org-my-model",
      modality: "text",
      task: "chat",
      techniques: [{ technique: "quantization" }],
      constraints: { max_memory_gb: 8, max_quality_drop: 0.05 },
      target_backend: "lemonade",
    });
  });

  it("omits constraints that are blank or invalid", () => {
    const preview = buildJobPreview(model({}), { ...draft, maxMemoryGb: "", maxQualityDrop: "-3" });

    expect(preview?.constraints).toEqual({});
  });

  it("keeps a zero quality-drop limit instead of treating it as no limit", () => {
    const preview = buildJobPreview(model({}), { ...draft, maxQualityDrop: "0" });

    expect(preview?.constraints.max_quality_drop).toBe(0);
  });

  it("returns nothing until a technique is chosen", () => {
    expect(buildJobPreview(model({}), { ...draft, techniques: [] })).toBeNull();
  });
});

describe("summarize", () => {
  const backend: BackendCapabilities = {
    backend: "lemonade",
    display_name: "Lemonade",
    kind: "local",
    availability: "available",
    capabilities: [
      { modality: "text", task: "chat", support: "documented", note: "POST /v1/chat/completions" },
      { modality: "text", task: "embedding", support: "planned", note: null },
      { modality: "video", task: null, support: "unsupported", note: "No endpoint" },
    ],
  };

  it("reports the strongest level declared for a modality", () => {
    expect(summarize(backend, "text")).toEqual({
      level: "documented",
      notes: ["Chat: POST /v1/chat/completions"],
    });
  });

  it("treats a modality with no declaration as unsupported", () => {
    expect(summarize(backend, "image").level).toBe("unsupported");
    expect(summarize(backend, "video").notes).toEqual(["No endpoint"]);
  });
});
