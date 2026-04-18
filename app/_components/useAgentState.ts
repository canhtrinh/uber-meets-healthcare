"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { usePrimVoices } from "primvoices-react";
import { emptyState, type AgentState } from "../lib/types";

/**
 * Subscribes to the agent's debug-message stream and mirrors the
 * most recent `state_update` CustomEvent into local React state.
 *
 * The VoiceRun agent yields `CustomEvent(name="state_update", data={"state": ...})`
 * after every tool call. The SDK surfaces those as entries in `debugMessages[]`
 * with `name === "state_update"` and `data.custom === true`.
 */
export function useAgentState() {
  const { debugMessages, sendTextEvent } = usePrimVoices();
  const [state, setState] = useState<AgentState>(emptyState());
  const lastSeen = useRef(0);

  useEffect(() => {
    if (!debugMessages || debugMessages.length === lastSeen.current) return;
    // Walk only new messages since last render.
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
      // Tell the agent the user edited something in the UI.
      // The system prompt instructs it to treat "[user-edit]" messages as authoritative.
      sendTextEvent(`[user-edit] ${path}=${JSON.stringify(value)}`);
    },
    [sendTextEvent],
  );

  const sendUserMessage = useCallback(
    (text: string) => sendTextEvent(text),
    [sendTextEvent],
  );

  return { state, sendUserEdit, sendUserMessage };
}
