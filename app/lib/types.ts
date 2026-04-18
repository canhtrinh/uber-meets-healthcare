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
  location: Location;
  candidates: Nurse[];
  booking: Booking | null;
}

export const emptyState = (): AgentState => ({
  patient: {},
  situation: { description: null, issueTags: [], urgency: null },
  preferences: {},
  location: { label: "Downtown SF", lat: 37.7749, lng: -122.4194 },
  candidates: [],
  booking: null,
});
