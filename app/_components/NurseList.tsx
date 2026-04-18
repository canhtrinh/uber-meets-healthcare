"use client";

import type { Nurse } from "../lib/types";

interface Props {
  nurses: Nurse[];
  selectedId: string | null;
  onSelect: (nurse: Nurse) => void;
}

export function NurseList({ nurses, selectedId, onSelect }: Props) {
  if (nurses.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-zinc-300 dark:border-zinc-700 px-5 py-8 text-center text-sm text-zinc-400">
        Nurses will appear once we know the situation.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-xs uppercase tracking-wider text-zinc-500 px-1">
        Matched nurses
      </h3>
      {nurses.map((n) => {
        const active = n.id === selectedId;
        return (
          <button
            key={n.id}
            onClick={() => onSelect(n)}
            className={`w-full text-left rounded-2xl border px-4 py-3 bg-white dark:bg-zinc-900 dark:border-zinc-800 shadow-sm transition-all ${
              active
                ? "ring-2 ring-emerald-500 border-emerald-500"
                : "hover:border-zinc-400 dark:hover:border-zinc-600"
            }`}
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-emerald-400 to-sky-500 flex items-center justify-center text-white font-semibold text-sm shrink-0">
                {initialsOf(n.name)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline justify-between gap-2">
                  <div className="font-medium truncate">{n.name}</div>
                  <div className="text-xs text-zinc-500 shrink-0">
                    ★ {n.rating.toFixed(1)} · {n.yearsExperience}y
                  </div>
                </div>
                <div className="text-xs text-zinc-500 truncate">
                  {n.canTreat.slice(0, 3).join(" · ")}
                </div>
                <div className="flex items-center gap-2 pt-1 text-xs">
                  <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                    <Dot /> {n.etaMinutes} min
                  </span>
                  <span className="text-zinc-400">·</span>
                  <span className="text-zinc-500">
                    {n.availableNow ? "Available now" : `Next: ${n.nextSlot}`}
                  </span>
                </div>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function Dot() {
  return (
    <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500" />
  );
}

function initialsOf(name: string) {
  return name
    .split(/[\s,]+/)
    .filter((w) => /[A-Za-z]/.test(w[0] ?? ""))
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}
