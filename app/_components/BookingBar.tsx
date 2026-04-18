"use client";

import { useState } from "react";
import type { Nurse } from "../lib/types";

interface Props {
  nurse: Nurse | null;
  onConfirm: (when: string) => void;
  onCancel: () => void;
}

const TIME_OPTIONS = (nextSlot: string) => [
  "Now",
  "Today 3:00 PM",
  "Tomorrow 9:00 AM",
  nextSlot,
].filter((v, i, a) => a.indexOf(v) === i);

export function BookingBar({ nurse, onConfirm, onCancel }: Props) {
  const [when, setWhen] = useState<string>("Now");

  if (!nurse) return null;

  const options = TIME_OPTIONS(nurse.nextSlot);

  // Default "Now" only if the nurse is actually available now.
  const effectiveWhen =
    when === "Now" && !nurse.availableNow ? nurse.nextSlot : when;

  return (
    <div className="fixed inset-x-0 bottom-0 border-t border-zinc-200 dark:border-zinc-800 bg-white/95 dark:bg-zinc-950/95 backdrop-blur px-4 py-3 sm:px-6">
      <div className="mx-auto max-w-5xl flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-400 to-sky-500 flex items-center justify-center text-white text-xs font-semibold">
            {nurse.name
              .split(/\s+/)
              .slice(0, 2)
              .map((w) => w[0])
              .join("")}
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium truncate">{nurse.name}</div>
            <div className="text-xs text-zinc-500">
              {nurse.etaMinutes} min away
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5 items-center">
          {options.map((opt) => (
            <button
              key={opt}
              onClick={() => setWhen(opt)}
              disabled={opt === "Now" && !nurse.availableNow}
              className={`px-2.5 py-1 rounded-full text-xs border transition-colors disabled:opacity-40 ${
                effectiveWhen === opt
                  ? "bg-black text-white border-black dark:bg-white dark:text-black dark:border-white"
                  : "bg-transparent text-zinc-600 dark:text-zinc-300 border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              }`}
            >
              {opt}
            </button>
          ))}
          <div className="flex-1" />
          <button
            onClick={onCancel}
            className="px-3 py-1.5 rounded-full text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(effectiveWhen)}
            className="px-4 py-1.5 rounded-full text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-500"
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
