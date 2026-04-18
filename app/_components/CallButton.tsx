"use client";

import { usePrimVoices } from "primvoices-react";
import { useEffect, useRef, useState } from "react";

export function CallButton() {
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

  const [inCall, setInCall] = useState(false);
  const [muted, setMuted] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const startedAt = useRef<number | null>(null);

  // Clean up mic/socket when the component unmounts.
  useEffect(() => {
    return () => {
      stopListening();
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Drive the call timer while the line is live.
  useEffect(() => {
    if (!inCall) {
      setSeconds(0);
      startedAt.current = null;
      return;
    }
    if (startedAt.current == null) startedAt.current = Date.now();
    const t = setInterval(() => {
      if (startedAt.current != null) {
        setSeconds(Math.floor((Date.now() - startedAt.current) / 1000));
      }
    }, 500);
    return () => clearInterval(t);
  }, [inCall]);

  // If the WS drops unexpectedly, reset the UI so the user can redial.
  useEffect(() => {
    if (inCall && !isConnected && startedAt.current != null) {
      setInCall(false);
      setMuted(false);
    }
  }, [inCall, isConnected]);

  const startCall = async () => {
    setMuted(false);
    setInCall(true);
    try {
      if (!isConnected) {
        // The hook's `connect` is typed as () => void but its runtime implementation
        // is async and awaitable — awaiting ensures the WS is actually open before
        // we try to open the mic. Without this, startListening silently bails on the
        // very first click because the SDK checks `isConnected` before calling
        // getUserMedia. Second click then works because the WS opened in the
        // background. Awaiting fixes the single-click UX.
        await (connect as unknown as () => Promise<void>)();
      }
      await startListening();
    } catch (e) {
      // Permission denied, mic unavailable, or WS failed — bail out.
      console.error(e);
      setInCall(false);
      disconnect();
    }
  };

  const endCall = () => {
    stopListening();
    disconnect();
    setInCall(false);
    setMuted(false);
  };

  const toggleMute = async () => {
    if (muted) {
      await startListening();
      setMuted(false);
    } else {
      stopListening();
      setMuted(true);
    }
  };

  if (!inCall) {
    return (
      <div className="flex flex-col items-center gap-3">
        <button
          onClick={startCall}
          aria-label="Call dispatcher"
          className="group relative w-44 h-44 rounded-full bg-emerald-600 hover:bg-emerald-500 text-white flex items-center justify-center shadow-xl shadow-emerald-600/30 transition-transform hover:scale-[1.02] active:scale-[0.98]"
        >
          <PhoneIcon className="w-14 h-14" />
        </button>
        <div className="text-sm font-medium text-zinc-700 dark:text-zinc-200">
          Call dispatcher
        </div>
        <div className="text-xs text-zinc-500 h-4">
          {error ? <span className="text-red-500">{error}</span> : ""}
        </div>
      </div>
    );
  }

  // In-call: waveform card, mute, hangup.
  const level = Math.min(1, audioStats?.level ?? 0);
  const status = error
    ? "Error"
    : muted
      ? "Muted"
      : isPlaying
        ? "Agent speaking…"
        : audioStats?.isSpeaking
          ? "Listening"
          : isConnected
            ? "Connected"
            : "Connecting…";

  return (
    <div className="flex flex-col items-center gap-5 w-full max-w-xs">
      <div className="w-full rounded-3xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-5 py-5 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                isConnected
                  ? isPlaying
                    ? "bg-sky-500"
                    : muted
                      ? "bg-zinc-400"
                      : "bg-emerald-500"
                  : "bg-amber-500"
              } ${isConnected && !muted ? "animate-pulse" : ""}`}
              aria-hidden
            />
            <span className="text-sm font-medium">{status}</span>
          </div>
          <div className="text-sm tabular-nums text-zinc-500">
            {formatClock(seconds)}
          </div>
        </div>
        <Waveform level={level} speaking={!!audioStats?.isSpeaking} muted={muted} playing={isPlaying} />
      </div>

      <div className="flex items-center gap-4">
        <RoundIconButton
          label={muted ? "Unmute microphone" : "Mute microphone"}
          onClick={toggleMute}
          tone={muted ? "muted" : "neutral"}
        >
          {muted ? <MicOffIcon className="w-5 h-5" /> : <MicIcon className="w-5 h-5" />}
        </RoundIconButton>
        <RoundIconButton
          label="End call"
          onClick={endCall}
          tone="danger"
          size="lg"
        >
          <HangupIcon className="w-7 h-7" />
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

function Waveform({
  level,
  speaking,
  muted,
  playing,
}: {
  level: number;
  speaking: boolean;
  muted: boolean;
  playing: boolean;
}) {
  const color = muted
    ? "bg-zinc-300 dark:bg-zinc-700"
    : playing
      ? "bg-sky-500"
      : speaking
        ? "bg-emerald-500"
        : "bg-zinc-300 dark:bg-zinc-700";

  const bars = 18;
  return (
    <div className="mt-4 flex items-center justify-center gap-1 h-10">
      {Array.from({ length: bars }).map((_, i) => {
        const center = (bars - 1) / 2;
        const d = Math.abs(i - center) / center;
        const amp = muted ? 0.12 : Math.max(0.12, level * (1 - d * 0.6));
        return (
          <span
            key={i}
            className={`inline-block w-1 rounded-full ${color} transition-all`}
            style={{
              height: `${10 + amp * 30}px`,
              opacity: muted ? 0.5 : 0.8 + amp * 0.2,
              transition: "height 80ms linear, opacity 120ms linear",
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
  size = "md",
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  tone?: "neutral" | "muted" | "danger";
  size?: "md" | "lg";
}) {
  const base =
    "rounded-full flex items-center justify-center shadow-md transition-transform active:scale-95";
  const sz = size === "lg" ? "w-16 h-16" : "w-12 h-12";
  const tones = {
    neutral:
      "bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-100 hover:bg-zinc-200 dark:hover:bg-zinc-700",
    muted:
      "bg-amber-500 text-white hover:bg-amber-400",
    danger: "bg-red-600 text-white hover:bg-red-500",
  };
  return (
    <button onClick={onClick} aria-label={label} className={`${base} ${sz} ${tones[tone]}`}>
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
