import { useState } from "react";
import { Link } from "react-router";

import { useModels, useSettings } from "../../lib/api";
import { formatBytes } from "../../lib/format";
import { ImageError, readImage, toDataUrl } from "../../lib/image";
import { imageLimit, metricsSource, modelKey, usableModels } from "../../lib/models";
import type { ChatMode as Mode } from "../../lib/models";
import type { GenerationSettings, ImageInput, ModelSpec } from "../../lib/types";
import { useChat } from "../../lib/useChat";
import { fieldClass, LocationBadge, Notice, Panel, QueryView } from "../ui";
import { ImagePicker } from "./ImagePicker";
import { Elapsed, MetricsPanel } from "./MetricsPanel";
import { ModelPicker } from "./ModelPicker";
import { Transcript } from "./Transcript";

const DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const SUGGESTION_COUNT = 3;

const EXAMPLES: Record<Mode, readonly string[]> = {
  text: [
    "Explain how quantization shrinks a language model.",
    "Write a Python function that checks whether a string is a palindrome.",
    "Give three differences between TCP and UDP.",
  ],
  vision: [
    "Describe this image.",
    "Identify visible objects.",
    "Read the text in this screenshot.",
    "Explain this technical diagram.",
    "Summarize the contents of this chart.",
  ],
};

function downloadSuggestions(models: ModelSpec[], mode: Mode): ModelSpec[] {
  return models
    .filter(
      (model) =>
        model.downloaded === false &&
        model.size_bytes !== null &&
        model.tasks.includes("chat") &&
        (mode === "text" || model.modalities.includes("vision")),
    )
    .sort((a, b) => (a.size_bytes ?? 0) - (b.size_bytes ?? 0))
    .slice(0, SUGGESTION_COUNT);
}

function NoModels({ models, mode }: { models: ModelSpec[]; mode: Mode }) {
  const suggestions = downloadSuggestions(models, mode);
  return (
    <Panel>
      <p className="font-medium">
        {mode === "vision" ? "No vision model is downloaded" : "No chat model is downloaded"}
      </p>
      <p className="mt-1 max-w-[65ch] text-sm text-muted">
        {mode === "vision"
          ? "Image understanding needs a model labelled vision. "
          : "Text generation needs a chat model. "}
        Antar never downloads models on its own. Choose one on the Models page; the smallest
        compatible ones Lemonade offers are listed here.
      </p>
      {suggestions.length > 0 && (
        <ul className="mt-4 space-y-1 text-sm">
          {suggestions.map((model) => (
            <li key={model.id} className="flex justify-between gap-4 border-b border-line/60 py-1.5 last:border-0">
              <span className="font-mono text-[0.8125rem]">{model.id}</span>
              <span className="tabular text-muted">{formatBytes(model.size_bytes)}</span>
            </li>
          ))}
        </ul>
      )}
      <Link
        to={mode === "vision" ? "/models?modality=vision" : "/models?modality=text"}
        className="mt-4 inline-block rounded-md border border-local/60 px-3 py-1.5 text-sm hover:bg-local/10"
      >
        Open the Models page
      </Link>
    </Panel>
  );
}

interface WorkspaceProps {
  models: ModelSpec[];
  mode: Mode;
  /** Something the user should know about a backend that is not answering. */
  notice?: string | null;
}

function Workspace({ models, mode, notice }: WorkspaceProps) {
  const settingsQuery = useSettings();
  const maxImageBytes = settingsQuery.data?.inference.max_image_bytes ?? DEFAULT_MAX_IMAGE_BYTES;
  const chat = useChat();
  const [selectedKey, setSelectedKey] = useState(models[0] ? modelKey(models[0]) : "");
  const [draft, setDraft] = useState("");
  const [images, setImages] = useState<ImageInput[]>([]);
  const [imageError, setImageError] = useState<string | null>(null);
  const [maxTokens, setMaxTokens] = useState(512);
  const [temperature, setTemperature] = useState(0.7);
  const [thinking, setThinking] = useState(true);

  const model = models.find((candidate) => modelKey(candidate) === selectedKey) ?? models[0];
  const cloud = model?.location === "cloud";
  const limit = imageLimit(model);
  const generating = chat.status === "generating";
  const started = chat.turns.length > 0;
  // In vision mode the first question must carry an image; later ones reuse it from history.
  const needsImage = mode === "vision" && !started && images.length === 0;
  const canSend = Boolean(model) && draft.trim() !== "" && !generating && !needsImage;
  const lastReply = chat.turns.findLast((turn) => turn.role === "assistant" && Boolean(turn.metrics || turn.stopped));

  const send = (text: string) => {
    if (!model || !text.trim() || generating || needsImage) return;
    // Sent for every model: some reason without being labelled as reasoning models,
    // and the backends ignore the option for models that cannot.
    const settings: GenerationSettings = { max_tokens: maxTokens, temperature, enable_thinking: thinking };
    void chat.send({
      backend: model.backend,
      model: model.id,
      text: text.trim(),
      images: !started && images.length > 0 ? images : undefined,
      settings,
    });
    setDraft("");
  };

  const chooseImage = async (file: File | undefined) => {
    if (!file) return;
    try {
      const loaded = await readImage(file, maxImageBytes);
      chat.reset();
      // A backend that takes one image replaces it; one that takes several adds to them.
      setImages((current) => (limit === 1 ? [loaded] : [...current, loaded].slice(0, limit)));
      setImageError(null);
    } catch (caught) {
      setImageError(caught instanceof ImageError ? caught.message : "That file could not be read.");
    }
  };

  const startOver = () => {
    chat.reset();
    setImages([]);
    setImageError(null);
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0 space-y-4">
        {notice && <Notice>{notice}</Notice>}
        <section className="flex min-h-[22rem] flex-col rounded-lg border border-line bg-surface">
          {model && (
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-5 py-2.5 text-sm" aria-label="Active model">
              <LocationBadge location={model.location} detail={model.provider} />
              <span className="font-mono text-xs break-all text-muted">{model.id}</span>
            </p>
          )}
          <div className="max-h-[60vh] flex-1 overflow-y-auto">
            <Transcript
              turns={chat.turns}
              status={chat.status}
              cloud={cloud}
              empty={
                <>
                  {mode === "vision" && images.length > 0 && (
                    <div className="mb-4 flex flex-wrap gap-2">
                      {images.map((image, position) => (
                        <img
                          key={position}
                          src={toDataUrl(image)}
                          alt="Selected for analysis"
                          className="max-h-64 rounded-md border border-line"
                        />
                      ))}
                    </div>
                  )}
                  <p className="text-sm text-muted">
                    {needsImage ? "Choose an image, then ask about it." : "Try one of these, or write your own."}
                  </p>
                  <ul className="mt-3 flex flex-wrap gap-2">
                    {EXAMPLES[mode].map((example) => (
                      <li key={example}>
                        <button
                          type="button"
                          disabled={needsImage || generating}
                          onClick={() => send(example)}
                          className="rounded-full border border-line px-3 py-1.5 text-left text-sm text-muted transition-colors hover:border-muted hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {example}
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              }
            />
          </div>

          {chat.error && (
            <div role="alert" className="mx-5 mb-4 rounded-md border border-down/50 bg-down/5 px-4 py-3 text-sm text-down">
              {chat.error}
            </div>
          )}

          <form
            className="border-t border-line p-4"
            onSubmit={(event) => {
              event.preventDefault();
              send(draft);
            }}
          >
            <label htmlFor="prompt" className="sr-only">
              {mode === "vision" ? "Question about the image" : "Prompt"}
            </label>
            <textarea
              id="prompt"
              rows={3}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  send(draft);
                }
              }}
              placeholder={mode === "vision" ? "Ask about the image" : "Write a prompt. Enter sends, Shift+Enter adds a line."}
              className={`${fieldClass} resize-y`}
            />
            <div className="mt-3 flex flex-wrap items-center gap-3">
              {generating ? (
                <button
                  type="button"
                  onClick={chat.stop}
                  className="rounded-md border border-down/60 px-4 py-2 text-sm text-down hover:bg-down/10"
                >
                  Stop generating
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!canSend}
                  className={`rounded-md px-4 py-2 text-sm font-medium text-ground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 ${cloud ? "bg-cloud" : "bg-local"}`}
                >
                  Send
                </button>
              )}
              {started && !generating && (
                <button type="button" onClick={startOver} className="rounded-md border border-line px-3 py-2 text-sm hover:border-muted">
                  New conversation
                </button>
              )}
              {generating && chat.startedAt !== null && (
                <span className="text-sm text-muted">
                  Generating, <Elapsed startedAt={chat.startedAt} />
                </span>
              )}
            </div>
          </form>
        </section>
      </div>

      <aside className="space-y-4">
        <ModelPicker
          models={models}
          model={model}
          disabled={generating}
          onChange={(key) => {
            setSelectedKey(key);
            startOver();
          }}
        />

        {mode === "vision" && (
          <ImagePicker
            images={images}
            limit={limit}
            cloud={cloud}
            maxBytes={maxImageBytes}
            disabled={generating}
            error={imageError}
            onChoose={(file) => void chooseImage(file)}
            onRemove={(position) => {
              chat.reset();
              setImages((current) => current.filter((_, index) => index !== position));
            }}
          />
        )}

        <Panel title="Generation settings">
          <div className="space-y-4">
            <div>
              <label htmlFor="max-tokens" className="mb-1.5 block text-sm">
                Maximum output tokens
              </label>
              <input
                id="max-tokens"
                type="number"
                min={1}
                max={16384}
                value={maxTokens}
                onChange={(event) => setMaxTokens(Math.min(16384, Math.max(1, Number(event.target.value) || 1)))}
                className={fieldClass}
              />
            </div>
            <div>
              <label htmlFor="temperature" className="mb-1.5 flex justify-between text-sm">
                Temperature <span className="tabular text-muted">{temperature.toFixed(1)}</span>
              </label>
              <input
                id="temperature"
                type="range"
                min={0}
                max={2}
                step={0.1}
                value={temperature}
                onChange={(event) => setTemperature(Number(event.target.value))}
                className={`w-full ${cloud ? "accent-(--color-cloud)" : "accent-(--color-local)"}`}
              />
            </div>
            <div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={thinking}
                  onChange={(event) => setThinking(event.target.checked)}
                  className={cloud ? "accent-(--color-cloud)" : "accent-(--color-local)"}
                />
                Let the model reason first
              </label>
              <p className="mt-1 text-xs text-faint">
                Only affects models that can reason. Reasoning counts toward the output limit.
              </p>
            </div>
          </div>
        </Panel>

        <Panel title="Last response">
          <MetricsPanel turn={lastReply} source={metricsSource(model)} />
        </Panel>
      </aside>
    </div>
  );
}

/** The shared text and vision chat surface. All inference goes through the Antar API. */
export function ChatWorkspace({ mode }: { mode: Mode }) {
  const models = useModels();
  return (
    <QueryView query={models}>
      {(inventory) => {
        const usable = usableModels(inventory.models, mode);
        const lemonade = inventory.sources.find((source) => source.backend === "lemonade");
        const lemonadeDown = lemonade !== undefined && lemonade.availability !== "available";
        if (usable.length === 0 && lemonade && lemonadeDown) {
          return (
            <Panel>
              <p className="font-medium text-down">Lemonade is not reachable</p>
              <p className="mt-1 max-w-[65ch] text-sm text-muted">{lemonade.detail}</p>
              <p className="mt-3 text-sm text-muted">
                Start the Lemonade server, then reload this page. Antar does not substitute simulated
                output when the server is down.
              </p>
            </Panel>
          );
        }
        return usable.length === 0 ? (
          <NoModels models={inventory.models} mode={mode} />
        ) : (
          // Remounting when the model list changes keeps the selection valid.
          <Workspace
            key={usable.map(modelKey).join("|")}
            models={usable}
            mode={mode}
            notice={lemonadeDown ? `Lemonade is not reachable, so only cloud models are listed. ${lemonade.detail}` : null}
          />
        );
      }}
    </QueryView>
  );
}
