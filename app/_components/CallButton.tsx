"use client";

import { usePrimVoices } from "primvoices-react";
import { useEffect, useRef, useState } from "react";

interface Props {
  inCall: boolean;
  setInCall: (v: boolean) => void;
}

export function CallButton({ inCall, setInCall }: Props) {
  const {
    connect,
    disconnect,
    startListening,
    stopListening,
    isConnected,
    isListening,
    isPlaying,
    audioStats,
    error,
  } = usePrimVoices();

  // User-controlled mute (separate from the auto-mute that happens while the
  // agent is speaking). Auto-gate logic lives in the effect below.
  const [userMuted, setUserMuted] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const startedAt = useRef<number | null>(null);
  const wasConnected = useRef(false);

  useEffect(() => {
    return () => {
      stopListening();
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Half-duplex gate: mic is open only when (a) we're in a call, (b) the WS is
  // up, (c) the agent is NOT currently speaking, (d) the user hasn't manually
  // muted. The explicit isListening guard prevents redundant start/stop calls
  // that would tangle the underlying getUserMedia stream. startListening and
  // stopListening are intentionally out of the dep array because they are not
  // guaranteed stable references from the SDK hook and would cause spurious
  // re-fires on every render.
  useEffect(() => {
    if (!inCall || !isConnected) return;
    const shouldListen = !isPlaying && !userMuted;
    if (shouldListen && !isListening) {
      startListening().catch((e) => console.error("[CallButton] startListening failed:", e));
    } else if (!shouldListen && isListening) {
      stopListening();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inCall, isConnected, isPlaying, userMuted, isListening]);

  useEffect(() => {
    if (!inCall || !isConnected) return;
    if (startedAt.current == null) startedAt.current = Date.now();
    const t = setInterval(() => {
      if (startedAt.current != null) {
        setSeconds(Math.floor((Date.now() - startedAt.current) / 1000));
      }
    }, 500);
    return () => clearInterval(t);
  }, [inCall, isConnected]);

  useEffect(() => {
    if (isConnected) {
      wasConnected.current = true;
      return;
    }
    if (inCall && wasConnected.current) {
      wasConnected.current = false;
      startedAt.current = null;
      setSeconds(0);
      setInCall(false);
      setUserMuted(false);
    }
  }, [inCall, isConnected, setInCall]);

  const startCall = async () => {
    setUserMuted(false);
    setInCall(true);
    try {
      if (!isConnected) {
        // Hook's connect is typed () => void but runtime-async; await ensures the
        // WS is open before startListening, so the very first click opens the mic
        // prompt (SDK's startListening silently bails if isConnected is false).
        await (connect as unknown as () => Promise<void>)();
      }
      // Kick off the first startListening in the same user-gesture promise
      // chain so the browser shows the mic permission prompt. After this,
      // the half-duplex effect above owns mic state.
      await startListening();
    } catch (e) {
      console.error(e);
      setInCall(false);
      disconnect();
    }
  };

  const endCall = () => {
    stopListening();
    disconnect();
    wasConnected.current = false;
    startedAt.current = null;
    setSeconds(0);
    setInCall(false);
    setUserMuted(false);
  };

  const toggleMute = () => {
    // The gate effect will pick this up and stop/start listening accordingly.
    setUserMuted((v) => !v);
  };

  const level = Math.min(1, audioStats?.level ?? 0);
  const status = error
    ? "Error"
    : userMuted
      ? "Muted"
      : isPlaying
        ? "Agent speaking…"
        : audioStats?.isSpeaking
          ? "Listening"
          : isConnected
            ? "Your turn"
            : "Connecting…";

  if (!inCall) {
    return (
      <div className="flex flex-col items-center gap-2 py-6">
        <button
          onClick={startCall}
          aria-label="Call dispatcher"
          className="group relative w-28 h-28 rounded-full bg-emerald-600 hover:bg-emerald-500 text-white flex items-center justify-center shadow-xl shadow-emerald-600/30 transition-transform hover:scale-[1.02] active:scale-[0.98]"
        >
          <PhoneIcon className="w-10 h-10" />
          <span className="absolute -inset-1 rounded-full border-2 border-emerald-400/40 animate-ping" />
        </button>
        <div className="text-sm font-medium text-zinc-700 dark:text-zinc-200">
          Tap to call
        </div>
        <div className="text-xs text-zinc-500 max-w-xs text-center leading-relaxed">
          Speak naturally. The details below fill in as we talk — tap any field
          to correct it.
        </div>
        {error && <div className="text-xs text-red-500 mt-1">{error}</div>}
      </div>
    );
  }

  return (
    <div className="sticky top-0 z-30 border-b border-zinc-200 dark:border-zinc-800 bg-white/95 dark:bg-zinc-950/95 backdrop-blur">
      <div className="mx-auto max-w-xl flex items-center gap-2 px-3 py-2 sm:gap-3 sm:px-4">
        <span
          className={`inline-block w-2 h-2 rounded-full shrink-0 ${
            isConnected
              ? isPlaying
                ? "bg-sky-500"
                : userMuted
                  ? "bg-zinc-400"
                  : "bg-emerald-500"
              : "bg-amber-500"
          } ${isConnected && !userMuted && !isPlaying ? "animate-pulse" : ""}`}
          aria-hidden
        />
        <span className="text-xs font-medium truncate flex-1 min-w-0">
          {status}
        </span>
        <MiniWaveform level={level} muted={userMuted || isPlaying} playing={isPlaying} />
        <span className="text-[11px] tabular-nums text-zinc-500 shrink-0">
          {formatClock(seconds)}
        </span>
        <RoundIconButton
          label={userMuted ? "Unmute microphone" : "Mute microphone"}
          onClick={toggleMute}
          tone={userMuted ? "muted" : "neutral"}
        >
          {userMuted ? (
            <MicOffIcon className="w-4 h-4" />
          ) : (
            <MicIcon className="w-4 h-4" />
          )}
        </RoundIconButton>
        <RoundIconButton label="End call" onClick={endCall} tone="danger">
          <HangupIcon className="w-4 h-4" />
        </RoundIconButton>
      </div>
    </div>
  );
}

function formatClock(total: number) {
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function MiniWaveform({
  level,
  muted,
  playing,
}: {
  level: number;
  muted: boolean;
  playing: boolean;
}) {
  const color = muted
    ? "bg-zinc-400 dark:bg-zinc-600"
    : playing
      ? "bg-sky-500"
      : "bg-emerald-500";
  const bars = 9;
  return (
    <div
      className="hidden xs:flex items-center gap-[2px] h-5 sm:flex shrink-0"
      aria-hidden
    >
      {Array.from({ length: bars }).map((_, i) => {
        const center = (bars - 1) / 2;
        const d = Math.abs(i - center) / center;
        const amp = muted ? 0.15 : Math.max(0.15, level * (1 - d * 0.5));
        return (
          <span
            key={i}
            className={`inline-block w-[2px] rounded-full ${color}`}
            style={{
              height: `${6 + amp * 12}px`,
              opacity: muted ? 0.4 : 0.85,
              transition: "height 80ms linear",
            }}
          />
        );
      })}
    </div>
  );
}

function RoundIconButton({
  label,
  onClick,
  children,
  tone = "neutral",
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  tone?: "neutral" | "muted" | "danger";
}) {
  const tones = {
    neutral:
      "bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-100 hover:bg-zinc-200 dark:hover:bg-zinc-700",
    muted: "bg-amber-500 text-white hover:bg-amber-400",
    danger: "bg-red-600 text-white hover:bg-red-500",
  };
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className={`rounded-full w-8 h-8 flex items-center justify-center shadow-sm transition-transform active:scale-95 shrink-0 ${tones[tone]}`}
    >
      {children}
    </button>
  );
}

function PhoneIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M20.01 15.38c-1.23 0-2.42-.2-3.53-.56-.35-.12-.74-.03-1.01.24l-1.57 1.97c-2.83-1.35-5.48-3.9-6.89-6.83l1.95-1.66c.27-.28.35-.67.24-1.02-.37-1.11-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45-.99-.99-.99z" />
    </svg>
  );
}

function HangupIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85-.18.18-.43.28-.7.28-.28 0-.53-.11-.71-.29L.29 13.08c-.18-.17-.29-.42-.29-.7 0-.28.11-.53.29-.71C3.34 8.78 7.46 7 12 7s8.66 1.78 11.71 4.67c.18.18.29.43.29.71 0 .28-.11.53-.29.71l-2.48 2.48c-.18.18-.43.29-.71.29-.27 0-.52-.1-.7-.28-.79-.74-1.69-1.36-2.67-1.85-.33-.16-.56-.5-.56-.9v-3.1C15.15 9.25 13.6 9 12 9z" />
    </svg>
  );
}

function MicIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z" />
    </svg>
  );
}

function MicOffIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.53-.98.83-2.1.83-3.28zm-4.02.17c0-.06.02-.11.02-.17V5c0-1.66-1.34-3-3-3S9 3.34 9 5v.18l5.98 5.99zM4.27 3L3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5.3-2.1-5.3-5.1H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c.91-.13 1.77-.45 2.54-.9L19.73 21 21 19.73 4.27 3z" />
    </svg>
  );
}
