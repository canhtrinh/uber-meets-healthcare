"use client";

import { useEffect, useState } from "react";
import { CallButton } from "./_components/CallButton";
import { StateView } from "./_components/StateView";
import { NurseList } from "./_components/NurseList";
import { BookingBar } from "./_components/BookingBar";
import { BookingConfirmation } from "./_components/BookingConfirmation";
import { useAgentState } from "./_components/useAgentState";
import type { Nurse } from "./lib/types";

export default function Page() {
  const { state, sendUserEdit, sendUserMessage } = useAgentState();
  const [inCall, setInCall] = useState(false);
  const [selectedNurse, setSelectedNurse] = useState<Nurse | null>(null);

  const selectedId = selectedNurse?.id ?? null;

  useEffect(() => {
    if (state.booking) setSelectedNurse(null);
  }, [state.booking]);

  const onConfirm = (when: string) => {
    if (!selectedNurse) return;
    sendUserMessage(
      `[user-pick] book nurseId=${selectedNurse.id} when="${when}"`,
    );
  };

  return (
    <div className="min-h-dvh flex flex-col">
      {!inCall && (
        <header className="px-4 pt-4 pb-1 max-w-xl w-full mx-auto">
          <div className="flex items-center gap-2">
            <LogoMark />
            <h1 className="text-base font-semibold tracking-tight">Nightingale</h1>
            <span className="text-[11px] text-zinc-400 ml-1">
              voice-first home nurse dispatch
            </span>
          </div>
        </header>
      )}

      <CallButton inCall={inCall} setInCall={setInCall} />

      <main className="flex-1 pb-28">
        <div className="max-w-xl w-full mx-auto px-3 sm:px-4 pt-3">
          {state.booking ? (
            <BookingConfirmation booking={state.booking} />
          ) : (
            <StateView state={state} onEdit={sendUserEdit} />
          )}
          <div className="mt-3">
            <NurseList
              nurses={state.candidates}
              selectedId={selectedId}
              onSelect={setSelectedNurse}
            />
          </div>
        </div>
      </main>

      {!state.booking && selectedNurse && (
        <BookingBar
          nurse={selectedNurse}
          onConfirm={onConfirm}
          onCancel={() => setSelectedNurse(null)}
        />
      )}
    </div>
  );
}

function LogoMark() {
  return (
    <div className="w-6 h-6 rounded-md bg-gradient-to-br from-emerald-500 to-sky-500 flex items-center justify-center text-white font-bold text-xs">
      N
    </div>
  );
}
