import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";
import { streamChat } from "./chatStream";
import type { ChatMessage, GenerationSettings, ImageInput, InferenceMetrics } from "./types";

export interface Turn {
  id: number;
  role: "user" | "assistant";
  content: string;
  reasoning: string;
  images?: ImageInput[];
  /** Set once generation finishes normally. */
  metrics?: InferenceMetrics;
  finishReason?: string | null;
  stopped?: boolean;
  /** Wall-clock time the browser waited, including the network. */
  elapsedMs?: number;
  /** The request for this question failed; it is shown but not sent again as history. */
  failed?: boolean;
}

export type ChatStatus = "idle" | "generating";

interface SendArgs {
  backend: string;
  model: string;
  text: string;
  images?: ImageInput[];
  settings: GenerationSettings;
}

/**
 * The conversation as the API should see it. An exchange that produced no answer
 * (it failed, or was stopped before any text arrived) is left out entirely, so the
 * history never contains an empty reply or two questions in a row.
 */
export function toApiMessages(turns: Turn[]): ChatMessage[] {
  const answered = turns.filter((turn, index) => {
    if (turn.role === "assistant") return turn.content.trim() !== "";
    const reply = turns[index + 1];
    return !turn.failed && (reply === undefined || reply.content.trim() !== "");
  });
  return answered.map((turn) => ({
    role: turn.role,
    content: turn.content,
    ...(turn.images && turn.images.length > 0 && { images: turn.images }),
  }));
}

/** One conversation: history, a streaming reply, cancellation, and the last error. */
export function useChat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const controller = useRef<AbortController | null>(null);
  const nextId = useRef(1);
  // Guards against a second submit landing before React re-renders the disabled button.
  const busy = useRef(false);

  useEffect(() => () => controller.current?.abort(), []);

  const patchLast = useCallback((patch: (turn: Turn) => Turn) => {
    setTurns((current) => current.map((turn, index) => (index === current.length - 1 ? patch(turn) : turn)));
  }, []);

  const send = useCallback(
    async ({ backend, model, text, images, settings }: SendArgs) => {
      if (busy.current) return;
      busy.current = true;

      const user: Turn = { id: nextId.current++, role: "user", content: text, reasoning: "", images };
      const reply: Turn = { id: nextId.current++, role: "assistant", content: "", reasoning: "" };
      const history = [...turns, user];
      setTurns([...history, reply]);
      setError(null);
      setStatus("generating");
      const began = performance.now();
      setStartedAt(began);

      // Tokens can arrive faster than the screen refreshes; apply them once per frame.
      let pending = { content: "", reasoning: "" };
      let frame = 0;
      const flush = () => {
        frame = 0;
        const { content, reasoning } = pending;
        pending = { content: "", reasoning: "" };
        patchLast((turn) => ({
          ...turn,
          content: turn.content + content,
          reasoning: turn.reasoning + reasoning,
        }));
      };

      const abort = new AbortController();
      controller.current = abort;
      try {
        const result = await streamChat(
          { backend, model, messages: toApiMessages(history), settings },
          {
            signal: abort.signal,
            onDelta: (content, reasoning) => {
              pending = { content: pending.content + content, reasoning: pending.reasoning + reasoning };
              frame ||= requestAnimationFrame(flush);
            },
          },
        );
        cancelAnimationFrame(frame);
        patchLast((turn) => ({
          ...turn,
          content: result.content,
          reasoning: result.reasoning ?? "",
          metrics: result.metrics,
          finishReason: result.finish_reason,
          elapsedMs: performance.now() - began,
        }));
      } catch (caught) {
        cancelAnimationFrame(frame);
        flush();
        if (caught instanceof DOMException && caught.name === "AbortError") {
          patchLast((turn) => ({ ...turn, stopped: true, elapsedMs: performance.now() - began }));
        } else {
          setError(caught instanceof ApiError ? caught.message : "Generation failed unexpectedly.");
          // Drop an empty reply and mark the question, so a retry does not resend it.
          setTurns((current) => {
            if (current.at(-1)?.content) return current;
            const kept = current.slice(0, -1);
            return kept.map((turn, index) => (index === kept.length - 1 ? { ...turn, failed: true } : turn));
          });
        }
      } finally {
        controller.current = null;
        busy.current = false;
        setStatus("idle");
        setStartedAt(null);
      }
    },
    [turns, patchLast],
  );

  const stop = useCallback(() => controller.current?.abort(), []);

  const reset = useCallback(() => {
    controller.current?.abort();
    setTurns([]);
    setError(null);
  }, []);

  return { turns, status, error, startedAt, send, stop, reset };
}
