import { describe, expect, it } from "vitest";

import { CLOUD_MODEL, CLOUD_UP, cloudStatus, comparisonReport, MOCK_SMALL, model, row, run, WORKLOADS } from "../test/fixtures";
import {
  connectionState,
  elapsedSeconds,
  gpuPollMs,
  memoryBar,
  parseAmount,
  readingOrUnavailable,
} from "./cloud";
import {
  chartMetrics,
  comparisonRequestCount,
  formatRowValue,
  groupRows,
  pairResponses,
  sideCandidates,
  splitWorkloads,
} from "./comparison";
import { UNAVAILABLE } from "./format";
import {
  filterModels,
  groupByLocation,
  imageLimit,
  metricsSource,
  NO_FILTERS,
  parseFilters,
  sizeBucket,
  usableModels,
} from "./models";
import type { FeasibilityEstimate } from "./types";

const LOCAL_SMALL = model({ parameter_count: 1_700_000_000 });
const LOCAL_UNKNOWN = model({ id: "Mystery-GGUF", parameter_count: null, loaded: false, state: "installed" });
const CATALOG_ONLY = model({ id: "Gemma-3-4b-it-GGUF", downloaded: false, loaded: false, state: "discovered" });
const ALL = [LOCAL_SMALL, LOCAL_UNKNOWN, CATALOG_ONLY, CLOUD_MODEL, MOCK_SMALL];
const ids = (models: { id: string }[]) => models.map((item) => item.id);

describe("model filters", () => {
  it("buckets only by a published parameter count and never guesses a missing one", () => {
    expect(sizeBucket({ parameter_count: 1_700_000_000 })).toBe("small");
    expect(sizeBucket({ parameter_count: 8_190_735_360 })).toBe("medium");
    expect(sizeBucket({ parameter_count: 32_762_123_264 })).toBe("large");
    expect(sizeBucket({ parameter_count: null })).toBe("unknown");
  });

  it("filters by location, size, running state, and backend together", () => {
    expect(ids(filterModels(ALL, { ...NO_FILTERS, location: "cloud" }))).toEqual([CLOUD_MODEL.id]);
    expect(ids(filterModels(ALL, { ...NO_FILTERS, size: "unknown" }))).toEqual([MOCK_SMALL.id, LOCAL_UNKNOWN.id, CATALOG_ONLY.id]);
    expect(ids(filterModels(ALL, { ...NO_FILTERS, location: "local", run: "idle" }))).toEqual([LOCAL_UNKNOWN.id, CATALOG_ONLY.id]);
    expect(ids(filterModels(ALL, { ...NO_FILTERS, backend: "amd_cloud", run: "running" }))).toEqual([CLOUD_MODEL.id]);
  });

  it("reads filters from the URL and ignores values it does not know", () => {
    const filters = parseFilters(new URLSearchParams("location=cloud&size=large&state=running&modality=smell&q=qwen"));

    expect(filters).toMatchObject({ location: "cloud", size: "large", run: "running", modality: null, search: "qwen" });
    expect(parseFilters(new URLSearchParams("location=mars&size=huge"))).toMatchObject({ location: null, size: null });
  });

  it("groups models by where they run, local first, leaving out empty groups", () => {
    expect(groupByLocation(ALL).map((group) => group.label)).toEqual(["Local", "Cloud", "Simulated"]);
  });
});

describe("chat across backends", () => {
  it("offers real chat models from every backend, local first so the default is never the cloud", () => {
    // The cloud model is running and sorts first by id, but a local model is still the default.
    expect(ids(usableModels(ALL, "text"))).toEqual([LOCAL_SMALL.id, LOCAL_UNKNOWN.id, CLOUD_MODEL.id]);
    expect(usableModels(ALL, "vision")).toEqual([]);
  });

  it("allows several images only where the backend accepts them", () => {
    expect(imageLimit(LOCAL_SMALL)).toBe(1);
    expect(imageLimit(CLOUD_MODEL)).toBe(4);
    expect(imageLimit(undefined)).toBe(1);
  });

  it("says vLLM reports no per-response timings instead of leaving the gap unexplained", () => {
    expect(metricsSource(CLOUD_MODEL)).toEqual({
      reporter: "vLLM",
      timingsReason: "vLLM reports token counts but no per-response timings",
    });
    expect(metricsSource(LOCAL_SMALL)).toEqual({ reporter: "Lemonade", timingsReason: null });
  });
});

describe("cloud connection", () => {
  const unavailable = (detail: string) =>
    cloudStatus({ endpoint_configured: true, status: { ...CLOUD_UP.status, availability: "unavailable", detail } });

  it("says connected only when the API reported the endpoint available", () => {
    expect(connectionState(cloudStatus())).toBe("not_configured");
    expect(connectionState(CLOUD_UP)).toBe("connected");
    expect(connectionState(unavailable("vLLM is starting: the model is still loading (503)."))).toBe("loading_model");
    expect(connectionState(unavailable("Could not connect to the cloud endpoint. Is the SSH tunnel open?"))).toBe("unreachable");
  });

  it("polls GPUs no faster than the server samples, and not at all without SSH", () => {
    expect(gpuPollMs(undefined)).toBe(false);
    expect(gpuPollMs({ ssh_configured: false, interval_seconds: null, sample: null, reason: "No SSH host." })).toBe(false);
    expect(gpuPollMs({ ssh_configured: true, interval_seconds: 30, sample: null, reason: null })).toBe(30_000);
    expect(gpuPollMs({ ssh_configured: true, interval_seconds: 2, sample: null, reason: null })).toBe(5_000);
  });

  it("shows a missing reading as unavailable and a real zero as zero", () => {
    expect(readingOrUnavailable(null, "W")).toBe(UNAVAILABLE);
    expect(readingOrUnavailable(undefined, "%")).toBe(UNAVAILABLE);
    expect(readingOrUnavailable(0, "%")).toBe("0 %");
  });
});

describe("cost inputs", () => {
  it("treats a blank or invalid amount as not entered, never as zero", () => {
    expect(parseAmount("")).toBeNull();
    expect(parseAmount("  ")).toBeNull();
    expect(parseAmount("-3")).toBeNull();
    expect(parseAmount("abc")).toBeNull();
    expect(parseAmount("0")).toBe(0);
    expect(parseAmount("2.75")).toBe(2.75);
  });

  it("counts instance time from the operator's start, frozen at a recorded stop", () => {
    const started = "2026-11-18T10:00:00Z";
    const now = Date.parse("2026-11-18T11:30:00Z");

    expect(elapsedSeconds({ instance_started_at: null, instance_stopped_at: null }, now)).toBeNull();
    expect(elapsedSeconds({ instance_started_at: started, instance_stopped_at: null }, now)).toBe(5400);
    expect(elapsedSeconds({ instance_started_at: started, instance_stopped_at: "2026-11-18T10:15:00Z" }, now)).toBe(900);
  });

  it("draws the memory budget on one scale, overflowing when the model does not fit", () => {
    const GB = 1e9;
    const estimate = {
      weights_bytes: 60 * GB,
      kv_cache_bytes: 30 * GB,
      runtime_overhead_bytes: 10 * GB,
      required_bytes: 100 * GB,
      usable_bytes: 45 * GB,
      total_bytes: 50 * GB,
    } as FeasibilityEstimate;

    const bar = memoryBar(estimate);

    expect(bar.segments.map((segment) => segment.fraction)).toEqual([0.6, 0.3, 0.1]);
    expect(bar.totalFraction).toBe(0.5);
    expect(bar.usableFraction).toBe(0.45);
  });
});

describe("comparison report", () => {
  it("formats a missing value as unavailable and never as zero", () => {
    expect(formatRowValue(null, "ms")).toBe(UNAVAILABLE);
    expect(formatRowValue(null, "ratio")).toBe(UNAVAILABLE);
    expect(formatRowValue(0.25, "ratio")).not.toBe(UNAVAILABLE);
    expect(formatRowValue(0.004, "ms")).toBe("0.0040 ms");
  });

  it("groups one workload's rows by what they measure, in a fixed order", () => {
    const rows = [
      row({ metric: "accuracy", label: "Automatic score", scope: "quality", measured_by: "scorer", unit: "ratio" }),
      row({ metric: "latency_ms_median", label: "Latency" }),
      row({ metric: "tokens_per_second_median", label: "Backend speed", scope: "model", measured_by: "backend" }),
      row({ metric: "latency_ms_median", label: "Latency", workload: "qa_exact" }),
    ];

    expect(groupRows(rows, "all").map((group) => group.scope)).toEqual(["end_to_end", "model", "quality"]);
    expect(groupRows(rows, "qa_exact")).toHaveLength(1);
  });

  it("leaves a chart out when neither side has the value, rather than drawing zeros", () => {
    const rows = [
      row({ metric: "latency_ms_median", label: "Latency", local: 120, cloud: null }),
      row({ metric: "decode_tokens_per_second_median", label: "Decode", unit: "tok/s" }),
    ];

    expect(chartMetrics(rows)).toEqual([expect.objectContaining({ metric: "latency_ms_median", local: 120, cloud: null })]);
  });

  it("offers cloud models only on the cloud side, and mocks on both for offline use", () => {
    const sides = sideCandidates(ALL);

    expect(ids(sides.local)).toEqual([LOCAL_SMALL.id, LOCAL_UNKNOWN.id, MOCK_SMALL.id]);
    expect(ids(sides.cloud)).toEqual([CLOUD_MODEL.id, MOCK_SMALL.id]);
  });

  it("separates scored workloads and counts both sides' requests", () => {
    const { scored, manual } = splitWorkloads(WORKLOADS);

    expect(ids(scored)).toEqual(["qa_exact", "code_tests"]);
    expect(ids(manual)).toEqual(["general_qa", "vision_basic"]);
    // general_qa has 4 prompts: (1 warm-up + 3 x 4 measured) per side.
    expect(comparisonRequestCount(WORKLOADS, ["general_qa"], 1, 3)).toBe(26);
  });

  it("pairs each prompt's first measured answer from both sides, even when one side is missing", () => {
    const local = comparisonReport().local;
    const scored = WORKLOADS.find((item) => item.id === "qa_exact");
    if (!local || !scored) throw new Error("fixtures have a local side and qa_exact");
    const report = comparisonReport({
      local: { ...local, workloads: [scored], runs: [run({ workload: "qa_exact", prompt_id: "q1", response: "Jupiter" })] },
      cloud: null,
    });

    const pairs = pairResponses(report);

    expect(pairs.map((pair) => pair.key)).toEqual(["qa_exact:q1", "qa_exact:q2"]);
    expect(pairs[0]?.local?.response).toBe("Jupiter");
    expect(pairs[0]?.cloud).toBeUndefined();
    expect(pairs[1]?.local).toBeUndefined();
  });
});
