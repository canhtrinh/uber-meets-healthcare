"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import type { PhotoRequest } from "../lib/types";

interface Props {
  request: PhotoRequest;
  onSend: (kind: PhotoRequest["kind"], base64Jpeg: string) => void;
  onCancel: () => void;
}

// Aggressive compression: the image rides a single websocket text frame via
// `sendTextEvent`, and PrimVoices' server enforces a max frame size. Keep the
// base64 payload comfortably under ~100 KB.
const MAX_EDGE_PX = 640;
const JPEG_QUALITY = 0.6;
const SEND_TIMEOUT_MS = 25_000;

type Stage = "idle" | "preview" | "sending";

export function CameraCapture({ request, onSend, onCancel }: Props) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [base64, setBase64] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Note: reset on a new request is handled by `key={requestedAt}` on the
  // parent's render, which fully remounts this component.

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const openCamera = () => {
    setError(null);
    fileInputRef.current?.click();
  };

  const handleFile = async (file: File) => {
    try {
      const { dataUrl, b64 } = await downscaleToJpeg(file);
      setPreviewUrl(dataUrl);
      setBase64(b64);
      setStage("preview");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't process that image");
      setStage("idle");
    }
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void handleFile(file);
  };

  const send = () => {
    if (!base64) return;
    setStage("sending");
    setError(null);
    onSend(request.kind, base64);
  };

  // Safety net: if the agent never echoes a state update (e.g. the websocket
  // dropped the frame because it was too large), surface an error and let the
  // user retake or cancel rather than spinning forever.
  useEffect(() => {
    if (stage !== "sending") return;
    const t = setTimeout(() => {
      setError("That took too long. Try a smaller photo or tap 'Not now'.");
      setStage("preview");
    }, SEND_TIMEOUT_MS);
    return () => clearTimeout(t);
  }, [stage]);

  const retake = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setBase64(null);
    setStage("idle");
    fileInputRef.current?.click();
  };

  return (
    <div className="fixed inset-x-0 bottom-0 z-20 border-t border-zinc-200 dark:border-zinc-800 bg-white/95 dark:bg-zinc-950/95 backdrop-blur px-4 py-3 sm:px-6">
      <div className="mx-auto max-w-5xl flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <CameraIcon kind={request.kind} />
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wider text-zinc-500">
              {labelForKind(request.kind)}
            </div>
            <div className="text-sm font-medium truncate">
              Send a photo of {request.prompt}
            </div>
            {error && (
              <div className="text-xs text-red-500 mt-0.5">{error}</div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {stage === "preview" && previewUrl && (
            <Image
              src={previewUrl}
              alt="preview"
              width={48}
              height={48}
              unoptimized
              className="h-12 w-12 rounded-md object-cover border border-zinc-300 dark:border-zinc-700"
            />
          )}

          {stage === "idle" && (
            <button
              onClick={openCamera}
              className="px-4 py-1.5 rounded-full text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-500"
            >
              Open camera
            </button>
          )}

          {stage === "preview" && (
            <>
              <button
                onClick={retake}
                className="px-3 py-1.5 rounded-full text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                Retake
              </button>
              <button
                onClick={send}
                className="px-4 py-1.5 rounded-full text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-500"
              >
                Send
              </button>
            </>
          )}

          {stage === "sending" && (
            <span className="px-4 py-1.5 text-sm text-zinc-500 inline-flex items-center gap-2">
              <Spinner /> Sending…
            </span>
          )}

          <button
            onClick={onCancel}
            disabled={stage === "sending"}
            className="px-3 py-1.5 rounded-full text-sm text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50"
          >
            Not now
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={onInputChange}
        className="hidden"
      />
    </div>
  );
}

function labelForKind(kind: PhotoRequest["kind"]) {
  switch (kind) {
    case "insurance":
      return "Insurance card";
    case "symptom":
      return "Symptom photo";
    case "document":
      return "Document";
    default:
      return "Photo";
  }
}

function CameraIcon({ kind }: { kind: PhotoRequest["kind"] }) {
  return (
    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-emerald-500 to-sky-500 flex items-center justify-center text-white shrink-0">
      {kind === "insurance" ? (
        <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="6" width="18" height="12" rx="2" />
          <path d="M3 10h18" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M4 8h3l2-2h6l2 2h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z" />
          <circle cx="12" cy="13" r="3.5" />
        </svg>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <span
      className="inline-block w-3.5 h-3.5 border-2 border-zinc-400 border-t-transparent rounded-full animate-spin"
      aria-hidden
    />
  );
}

/**
 * Load a File into an HTMLImageElement, draw onto a canvas resized so the
 * long edge is <= MAX_EDGE_PX, and export as a JPEG data URL.
 *
 * Returns both the data URL (for in-page preview) and the bare base64 payload
 * (for shipping to the agent without the data: prefix).
 */
async function downscaleToJpeg(
  file: File,
): Promise<{ dataUrl: string; b64: string }> {
  const objectUrl = URL.createObjectURL(file);
  try {
    const img = await loadImage(objectUrl);
    const longEdge = Math.max(img.naturalWidth, img.naturalHeight);
    const scale = longEdge > MAX_EDGE_PX ? MAX_EDGE_PX / longEdge : 1;
    const w = Math.round(img.naturalWidth * scale);
    const h = Math.round(img.naturalHeight * scale);

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas not supported");
    ctx.drawImage(img, 0, 0, w, h);
    const dataUrl = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
    const b64 = dataUrl.split(",")[1] ?? "";
    return { dataUrl, b64 };
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    // Using document.createElement to avoid the global `Image` constructor
    // being shadowed by the imported `next/image` `Image` component.
    const img = document.createElement("img");
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Couldn't read that image"));
    img.src = src;
  });
}
