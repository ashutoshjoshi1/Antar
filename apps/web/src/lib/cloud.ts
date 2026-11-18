import { formatBytes, UNAVAILABLE } from "./format";
import type { CloudStatus, CostEstimate, FeasibilityEstimate, GpuTelemetry } from "./types";

export type ConnectionState = "not_configured" | "loading_model" | "unreachable" | "connected";

// The API reports a loading vLLM as "unavailable" and says so only in the detail text.
const LOADING_PATTERN = /still loading|is starting/i;

/** What the API reported about the cloud endpoint. "Connected" only when it said so. */
export function connectionState(status: CloudStatus): ConnectionState {
  if (!status.endpoint_configured || status.status.availability === "not_configured") {
    return "not_configured";
  }
  if (status.status.availability === "available") return "connected";
  return LOADING_PATTERN.test(status.status.detail) ? "loading_model" : "unreachable";
}

const MIN_GPU_POLL_MS = 5_000;

/** The server caches GPU samples for its interval; asking faster only returns the same one. */
export function gpuPollMs(telemetry: GpuTelemetry | undefined): number | false {
  if (!telemetry?.ssh_configured || telemetry.interval_seconds === null) return false;
  return Math.max(MIN_GPU_POLL_MS, telemetry.interval_seconds * 1000);
}

export function bytesOrUnavailable(bytes: number | null | undefined): string {
  return bytes === null || bytes === undefined ? UNAVAILABLE : formatBytes(bytes);
}

/** A reading with its unit, or "Unavailable". A missing reading is never shown as zero. */
export function readingOrUnavailable(value: number | null | undefined, unit: string, digits = 0): string {
  return value === null || value === undefined ? UNAVAILABLE : `${value.toFixed(digits)} ${unit}`;
}

/**
 * Seconds the instance has existed according to the operator's own start and
 * stop times. Ticks in the browser from the server's start time.
 */
export function elapsedSeconds(
  estimate: Pick<CostEstimate, "instance_started_at" | "instance_stopped_at">,
  nowMs: number,
): number | null {
  if (!estimate.instance_started_at) return null;
  const started = Date.parse(estimate.instance_started_at);
  const ended = estimate.instance_stopped_at ? Date.parse(estimate.instance_stopped_at) : nowMs;
  if (Number.isNaN(started) || Number.isNaN(ended)) return null;
  return Math.max(0, (ended - started) / 1000);
}

/** A datetime-local input value in the browser's zone, as an ISO timestamp with a timezone. */
export function localInputToIso(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** An ISO timestamp as a datetime-local input value in the browser's zone. */
export function isoToLocalInput(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** A blank field means "not entered" and is sent as null, never as zero. */
export function parseAmount(value: string): number | null {
  if (value.trim() === "") return null;
  const amount = Number(value);
  return Number.isFinite(amount) && amount >= 0 ? amount : null;
}

export const BYTES_PER_GB = 1_000_000_000;

export interface MemorySegment {
  key: "weights" | "kv_cache" | "overhead";
  label: string;
  bytes: number;
  /** Share of the bar, which spans the larger of total memory and what is required. */
  fraction: number;
}

export interface MemoryBar {
  segments: MemorySegment[];
  /** Where vLLM's usable reservation ends on the same scale. */
  usableFraction: number;
  totalFraction: number;
}

export function memoryBar(estimate: FeasibilityEstimate): MemoryBar {
  const scale = Math.max(estimate.total_bytes, estimate.required_bytes, 1);
  const segment = (key: MemorySegment["key"], label: string, bytes: number): MemorySegment => ({
    key,
    label,
    bytes,
    fraction: bytes / scale,
  });
  return {
    segments: [
      segment("weights", "Weights", estimate.weights_bytes),
      segment("kv_cache", "KV cache", estimate.kv_cache_bytes),
      segment("overhead", "Runtime overhead", estimate.runtime_overhead_bytes),
    ],
    usableFraction: estimate.usable_bytes / scale,
    totalFraction: estimate.total_bytes / scale,
  };
}
