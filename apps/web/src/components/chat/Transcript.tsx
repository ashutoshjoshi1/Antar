import { useEffect, useRef } from "react";

import { toDataUrl } from "../../lib/image";
import type { ChatStatus, Turn } from "../../lib/useChat";
import { Tag } from "../ui";

function Reply({ turn, generating }: { turn: Turn; generating: boolean }) {
  const waiting = generating && !turn.content && !turn.reasoning;
  return (
    <div className="max-w-[72ch]">
      {turn.reasoning && (
        <details open={generating && !turn.content} className="mb-3 rounded-md border border-line bg-ground/50">
          <summary className="cursor-pointer px-3 py-2 text-xs text-muted select-none">
            Reasoning{generating && !turn.content ? "…" : ""}
          </summary>
          <p className="border-t border-line px-3 py-2 text-sm whitespace-pre-wrap text-muted">
            {turn.reasoning}
          </p>
        </details>
      )}
      {waiting ? (
        <p className="text-sm text-muted" role="status">
          Waiting for the first token…
        </p>
      ) : (
        <p className="leading-relaxed whitespace-pre-wrap">
          {turn.content}
          {generating && <span aria-hidden className="ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 bg-local" />}
        </p>
      )}
      {!generating && !turn.content && turn.reasoning && turn.finishReason === "length" && (
        <p className="text-sm text-muted">
          The model used its whole output limit on reasoning and gave no answer. Raise the maximum
          output tokens, or turn reasoning off, and ask again.
        </p>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        {turn.stopped && <Tag tone="warn">Stopped</Tag>}
        {turn.finishReason === "length" && <Tag tone="warn">Cut off at the output limit</Tag>}
      </div>
    </div>
  );
}

interface TranscriptProps {
  turns: Turn[];
  status: ChatStatus;
  empty: React.ReactNode;
}

export function Transcript({ turns, status, empty }: TranscriptProps) {
  const end = useRef<HTMLDivElement>(null);
  const last = turns.at(-1);
  useEffect(() => {
    // Follow the reply as it grows; scrollIntoView is absent in some test environments.
    end.current?.scrollIntoView?.({ block: "nearest" });
  }, [last?.content, last?.reasoning]);

  if (turns.length === 0) return <div className="p-5">{empty}</div>;

  return (
    <ol className="space-y-6 p-5" aria-live="polite" aria-busy={status === "generating"}>
      {turns.map((turn, index) => (
        <li key={turn.id}>
          <p className={`mb-1.5 text-xs ${turn.role === "user" ? "text-muted" : "text-local"}`}>
            {turn.role === "user" ? "You" : "Model"}
          </p>
          {turn.role === "user" ? (
            <div className="max-w-[72ch]">
              {turn.image && (
                <img
                  src={toDataUrl(turn.image)}
                  alt="Uploaded for this question"
                  className="mb-2 max-h-56 rounded-md border border-line"
                />
              )}
              <p className="whitespace-pre-wrap">{turn.content}</p>
            </div>
          ) : (
            <Reply turn={turn} generating={status === "generating" && index === turns.length - 1} />
          )}
        </li>
      ))}
      <div ref={end} />
    </ol>
  );
}
