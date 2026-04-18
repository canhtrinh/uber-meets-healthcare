"use client";

import type { Booking } from "../lib/types";

export function BookingConfirmation({ booking }: { booking: Booking }) {
  return (
    <div className="rounded-2xl border border-emerald-500 bg-emerald-50 dark:bg-emerald-950/30 px-5 py-5 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-emerald-600 text-white flex items-center justify-center text-xl">
          ✓
        </div>
        <div>
          <div className="text-sm uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
            Booked
          </div>
          <div className="font-medium text-lg">
            {booking.nurseName} · {booking.when}
          </div>
        </div>
      </div>
      {booking.etaMinutes != null && (
        <div className="mt-3 text-sm text-emerald-800 dark:text-emerald-300">
          ETA {booking.etaMinutes} minutes. You&apos;ll get an SMS when they&apos;re on the
          way.
        </div>
      )}
    </div>
  );
}
