import { ACCEPT_ATTRIBUTE, toDataUrl } from "../../lib/image";
import type { ImageInput } from "../../lib/types";
import { Panel } from "../ui";

interface ImagePickerProps {
  images: ImageInput[];
  /** How many images the selected model's backend accepts in one message. */
  limit: number;
  cloud: boolean;
  maxBytes: number;
  disabled: boolean;
  error: string | null;
  onChoose: (file: File | undefined) => void;
  onRemove: (position: number) => void;
}

export function ImagePicker({ images, limit, cloud, maxBytes, disabled, error, onChoose, onRemove }: ImagePickerProps) {
  const single = limit === 1;
  const full = !single && images.length >= limit;
  const prompt = single
    ? images.length > 0
      ? "Choose a different image"
      : "Choose an image"
    : images.length > 0
      ? `Add another image (${images.length} of ${limit})`
      : "Choose an image";
  return (
    <Panel title={single ? "Image" : "Images"}>
      {images.length > 0 && (
        <ul className="mb-3 flex flex-wrap gap-2">
          {images.map((image, position) => (
            <li key={position} className="relative">
              <img src={toDataUrl(image)} alt="Selected for analysis" className="max-h-40 rounded-md border border-line" />
              {!single && (
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onRemove(position)}
                  className="mt-1 block text-xs text-muted underline hover:text-ink"
                >
                  Remove image {position + 1}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {full ? (
        <p className="text-sm text-muted">{limit} images is the most one message can carry.</p>
      ) : (
        <label className="block cursor-pointer rounded-md border border-dashed border-line px-3 py-2.5 text-center text-sm text-muted transition-colors focus-within:outline-2 focus-within:outline-local hover:border-muted hover:text-ink">
          {prompt}
          <input
            type="file"
            accept={ACCEPT_ATTRIBUTE}
            disabled={disabled}
            className="sr-only"
            onChange={(event) => {
              onChoose(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </label>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-down">
          {error}
        </p>
      )}
      <p className="mt-2 text-xs text-faint">
        PNG, JPEG, or WebP up to {Math.floor(maxBytes / 1024 / 1024)} MB.{" "}
        {cloud
          ? `Up to ${limit} images per message. They are sent to the configured cloud endpoint and Antar does not save them.`
          : "One image per message. The image goes to your local Lemonade server only and is not saved."}
      </p>
    </Panel>
  );
}
