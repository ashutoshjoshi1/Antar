import { ApiError, request } from "./api";
import type { ChatBody, ChatResult, ChatStreamEvent } from "./types";

/** Split a buffer of Server-Sent Events into complete events and the unfinished tail. */
export function splitEvents(buffer: string): { events: ChatStreamEvent[]; rest: string } {
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events = blocks.flatMap((block) =>
    block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => JSON.parse(line.slice("data:".length)) as ChatStreamEvent),
  );
  return { events, rest };
}

interface StreamOptions {
  signal: AbortSignal;
  onDelta: (content: string, reasoning: string) => void;
}

/**
 * Run one streamed chat request through the Antar API. Resolves with the final
 * result; rejects with ApiError on failure, or AbortError when `signal` aborts.
 * Aborting closes the connection, which stops generation on the server.
 */
export async function streamChat(body: ChatBody, { signal, onDelta }: StreamOptions): Promise<ChatResult> {
  const response = await request("/api/v1/inference/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.body) throw new ApiError("The Antar API returned an empty stream.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    const parsed = splitEvents(buffer + decoder.decode(value, { stream: true }));
    buffer = parsed.rest;
    for (const event of parsed.events) {
      if (event.type === "delta") onDelta(event.content, event.reasoning);
      else if (event.type === "done") return event.result;
      else throw new ApiError(event.message);
    }
  }
  throw new ApiError("The response ended before generation finished.");
}
