import type { ImageInput, ImageMediaType } from "./types";

const ACCEPTED: readonly ImageMediaType[] = ["image/png", "image/jpeg", "image/webp"];
export const ACCEPT_ATTRIBUTE = ACCEPTED.join(",");

export class ImageError extends Error {}

function isAccepted(type: string): type is ImageMediaType {
  return ACCEPTED.some((accepted) => accepted === type);
}

/** Why a file can't be used, or null if it can. */
export function rejectReason(file: { type: string; size: number }, maxBytes: number): string | null {
  if (!isAccepted(file.type)) return "Use a PNG, JPEG, or WebP image.";
  if (file.size > maxBytes) {
    return `That image is ${(file.size / 1024 / 1024).toFixed(1)} MB. The limit is ${Math.floor(maxBytes / 1024 / 1024)} MB.`;
  }
  return null;
}

/** Read an image into memory as base64. Nothing is uploaded until a question is sent. */
export async function readImage(file: File, maxBytes: number): Promise<ImageInput> {
  const reason = rejectReason(file, maxBytes);
  if (reason || !isAccepted(file.type)) throw new ImageError(reason ?? "Unsupported image.");
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const CHUNK = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + CHUNK));
  }
  return { media_type: file.type, data_base64: btoa(binary) };
}

export function toDataUrl(image: ImageInput): string {
  return `data:${image.media_type};base64,${image.data_base64}`;
}
