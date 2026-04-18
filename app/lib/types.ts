export type Urgency = "now" | "soon" | "scheduled";

export interface Patient {
  name?: string;
  age?: number;
  livesAlone?: boolean;
}

export interface Situation {
  description: string | null;
  issueTags: string[];
  urgency: Urgency | null;
}

export interface Preferences {
  language?: string;
  genderPref?: "f" | "m";
}

export interface EmergencyContact {
  name?: string;
  phone?: string;
  relationship?: string;
}

export interface Insurance {
  provider?: string;
  memberId?: string;
}

export interface Location {
  label?: string;
  lat: number;
  lng: number;
}

export interface Nurse {
  id: string;
  name: string;
  photo: string;
  canTreat: string[];
  languages: string[];
  lat: number;
  lng: number;
  availableNow: boolean;
  nextSlot: string;
  rating: number;
  yearsExperience: number;
  gender: "f" | "m";
  etaMinutes: number;
}

export interface Booking {
  nurseId: string;
  nurseName: string;
  when: string;
  etaMinutes: number | null;
}

export interface AgentState {
  patient: Patient;
  situation: Situation;
  preferences: Preferences;
  emergencyContact: EmergencyContact;
  insurance: Insurance;
  location: Location;
  candidates: Nurse[];
  booking: Booking | null;
}

export const emptyState = (): AgentState => ({
  patient: {},
  situation: { description: null, issueTags: [], urgency: null },
  preferences: {},
  emergencyContact: {},
  insurance: {},
  location: { label: "Downtown SF", lat: 37.7749, lng: -122.4194 },
  candidates: [],
  booking: null,
});

/**
 * Human-friendly ETA string for minutes.
 *   45   -> "45 min"
 *   60   -> "1 hr"
 *   120  -> "2 hr"
 *   135  -> "2 hr 15 min"
 */
export function formatEta(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (m === 0) return `${h} hr`;
  return `${h} hr ${m} min`;
}
