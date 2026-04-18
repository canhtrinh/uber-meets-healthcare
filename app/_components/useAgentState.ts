"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { usePrimVoices } from "primvoices-react";
import {
  emptyState,
  type AgentState,
  type Urgency,
  type Preferences,
  type Patient,
  type EmergencyContact,
  type Insurance,
} from "../lib/types";

/**
 * Mirrors the agent's state_update CustomEvents into local React state, AND
 * accepts optimistic user edits so the UI feels instant.
 *
 * Flow for a user edit:
 *   1. Local state updates immediately (so the toggle/input reflects the change).
 *   2. `sendTextEvent("[user-edit] path=value")` tells the agent.
 *   3. Agent eventually emits its own state_update, which overwrites (confirming
 *      or correcting the local edit).
 */
export function useAgentState() {
  const { debugMessages, sendTextEvent } = usePrimVoices();
  const [state, setState] = useState<AgentState>(emptyState());
  const lastSeen = useRef(0);

  useEffect(() => {
    if (!debugMessages || debugMessages.length === lastSeen.current) return;
    for (let i = lastSeen.current; i < debugMessages.length; i++) {
      const msg = debugMessages[i];
      if (msg?.name !== "state_update") continue;
      const next = (msg.data as { state?: AgentState } | undefined)?.state;
      if (next) setState(next);
    }
    lastSeen.current = debugMessages.length;
  }, [debugMessages]);

  const sendUserEdit = useCallback(
    (path: string, value: unknown) => {
      setState((prev) => applyEdit(prev, path, value));
      try {
        sendTextEvent(`[user-edit] ${path}=${JSON.stringify(value)}`);
      } catch {
        // No active call yet — the edit is still applied locally for UX.
      }
    },
    [sendTextEvent],
  );

  const sendUserMessage = useCallback(
    (text: string) => {
      try {
        sendTextEvent(text);
      } catch {
        /* ignore — not connected */
      }
    },
    [sendTextEvent],
  );

  return { state, sendUserEdit, sendUserMessage };
}

/**
 * Apply a local edit to the state. `path` is "section.field" (e.g.
 * "patient.age", "situation.urgency", "preferences.genderPref").
 * Unknown paths are ignored.
 */
function applyEdit(state: AgentState, path: string, value: unknown): AgentState {
  const [section, field] = path.split(".");
  if (!section || !field) return state;

  switch (section) {
    case "patient": {
      const patient: Patient = { ...state.patient };
      if (value === null || value === undefined) {
        delete patient[field as keyof Patient];
      } else {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (patient as any)[field] = value;
      }
      return { ...state, patient };
    }
    case "situation": {
      const situation = { ...state.situation };
      if (field === "urgency") {
        situation.urgency = (value as Urgency | null) ?? null;
      } else if (field === "description") {
        situation.description = typeof value === "string" ? value : null;
      } else if (field === "issueTags" && Array.isArray(value)) {
        situation.issueTags = value as string[];
      }
      return { ...state, situation };
    }
    case "preferences": {
      const preferences: Preferences = { ...state.preferences };
      if (value === null || value === undefined) {
        delete preferences[field as keyof Preferences];
      } else {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (preferences as any)[field] = value;
      }
      return { ...state, preferences };
    }
    case "emergencyContact": {
      const ec: EmergencyContact = { ...state.emergencyContact };
      if (value === null || value === undefined || value === "") {
        delete ec[field as keyof EmergencyContact];
      } else {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (ec as any)[field] = value;
      }
      return { ...state, emergencyContact: ec };
    }
    case "insurance": {
      const ins: Insurance = { ...state.insurance };
      if (value === null || value === undefined || value === "") {
        delete ins[field as keyof Insurance];
      } else {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (ins as any)[field] = value;
      }
      return { ...state, insurance: ins };
    }
    default:
      return state;
  }
}
