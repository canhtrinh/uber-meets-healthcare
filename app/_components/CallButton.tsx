"use client";

import { usePrimVoices } from "primvoices-react";
import { useEffect } from "react";

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

  // Clean up mic on unmount.
  useEffect(() => {
    return () => {
      stopListening();
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onClick = async () => {
    if (!isConnected) {
      connect();
    }
    if (isListening) {
      stopListening();
    } else {
      await startListening();
    }
  };

  const level = Math.min(1, audioStats?.level ?? 0);
  const label = error
    ? "Retry"
    : isListening
      ? "Tap to stop"
      : isConnected
        ? "Tap to speak"
        : "Tap to call";

  return (
    <div className="flex flex-col items-center gap-3">
      <button
        onClick={onClick}
        aria-label={label}
        className="group relative w-44 h-44 rounded-full bg-black text-white dark:bg-white dark:text-black flex items-center justify-center shadow-xl transition-transform hover:scale-[1.02] active:scale-[0.98] disabled:opacity-60"
      >
        {/* pulsing ring while listening or playing */}
        <span
          className={`absolute inset-0 rounded-full border-2 transition-opacity ${
            isListening
              ? "border-emerald-400 animate-ping"
              : isPlaying
                ? "border-sky-400 animate-ping"
                : "opacity-0"
          }`}
          aria-hidden
        />
        {/* audio level fill */}
        <span
          className="absolute inset-[6px] rounded-full bg-white/10 dark:bg-black/10"
          style={{
            transform: `scale(${0.85 + level * 0.2})`,
            transition: "transform 80ms linear",
          }}
          aria-hidden
        />
        <span className="relative text-center text-sm font-medium tracking-tight px-4">
          {label}
        </span>
      </button>
      <div className="text-xs text-zinc-500 dark:text-zinc-400 h-4">
        {error ? (
          <span className="text-red-500">{error}</span>
        ) : isListening ? (
          audioStats?.isSpeaking
            ? "listening…"
            : "listening"
        ) : isPlaying ? (
          "agent speaking"
        ) : isConnected ? (
          "connected"
        ) : (
          ""
        )}
      </div>
    </div>
  );
}
