"use client";

import { Card } from "./StateView";
import type { SymptomObservation } from "../lib/types";

interface Props {
  observations: SymptomObservation[];
}

export function ObservationsView({ observations }: Props) {
  if (observations.length === 0) return null;
  return (
    <Card title="Photo notes">
      <ul className="space-y-2">
        {observations.map((o, i) => (
          <li key={i} className="text-sm">
            <div className="text-xs uppercase tracking-wider text-zinc-500">
              {o.area}
            </div>
            <div className="text-zinc-800 dark:text-zinc-200">{o.findings}</div>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-zinc-400 italic">
        Visual impressions only — the visiting nurse will assess in person.
      </p>
    </Card>
  );
}
