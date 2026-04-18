"use client";

import { useEffect, useMemo, useState } from "react";
import { CallButton } from "./_components/CallButton";
import { StateView } from "./_components/StateView";
import { NurseList } from "./_components/NurseList";
import { BookingBar } from "./_components/BookingBar";
import { BookingConfirmation } from "./_components/BookingConfirmation";
import { useAgentState } from "./_components/useAgentState";
import type { Nurse } from "./lib/types";

export default function Page() {
  const { state, sendUserEdit, sendUserMessage } = useAgentState();
  const [selectedNurse, setSelectedNurse] = useState<Nurse | null>(null);

  // If the agent re-ranks and the selected nurse is no longer in the list,
  // keep the selection until the user picks a different one — it may just be
  // filtered out mid-flight.
  const selectedId = selectedNurse?.id ?? null;

  // Once a booking lands in state, clear the picker.
  useEffect(() => {
    if (state.booking) setSelectedNurse(null);
  }, [state.booking]);

  const onConfirm = (when: string) => {
    if (!selectedNurse) return;
    sendUserMessage(
      `[user-pick] book nurseId=${selectedNurse.id} when="${when}"`,
    );
  };

  const situationReady =
    state.situation.issueTags.length > 0 || state.candidates.length > 0;

  return (
    <div className="min-h-dvh flex flex-col">
      <header className="px-6 pt-6 pb-2 sm:px-10 sm:pt-10 max-w-5xl w-full mx-auto">
        <div className="flex items-center gap-2">
          <LogoMark />
          <h1 className="text-lg font-semibold tracking-tight">Nightingale</h1>
          <span className="text-xs text-zinc-400 ml-2 hidden sm:block">
            voice-first home nurse dispatch
          </span>
        </div>
      </header>

      <main className="flex-1 px-6 pb-32 sm:px-10 max-w-5xl w-full mx-auto">
        <div className="grid gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
          <section className="flex flex-col items-center justify-center py-10 md:py-20 md:sticky md:top-10 md:self-start">
            <div className="text-center mb-6">
              <div className="text-sm text-zinc-500 mb-1">
                {state.booking
                  ? "Your nurse is booked"
                  : situationReady
                    ? "Still there?"
                    : "Tap to talk to a dispatcher"}
              </div>
              <div className="text-2xl font-semibold tracking-tight">
                {state.booking
                  ? `${state.booking.nurseName}`
                  : state.patient.name
                    ? `Hi ${state.patient.name}`
                    : "We can help"}
              </div>
            </div>
            <CallButton />
            <p className="mt-6 max-w-xs text-center text-xs text-zinc-500">
              Speak freely. What you say fills the panel on the right — you can
              also tap any field there to correct it.
            </p>
          </section>

          <section className="py-4">
            {state.booking ? (
              <BookingConfirmation booking={state.booking} />
            ) : (
              <StateView state={state} onEdit={sendUserEdit} />
            )}
            <div className="mt-5">
              <NurseList
                nurses={state.candidates}
                selectedId={selectedId}
                onSelect={setSelectedNurse}
              />
            </div>
          </section>
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
    <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-500 to-sky-500 flex items-center justify-center text-white font-bold text-sm">
      N
    </div>
  );
}
