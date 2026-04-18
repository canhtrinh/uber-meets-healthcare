"use client";

import { useState } from "react";
import type { AgentState, Urgency } from "../lib/types";

interface Props {
  state: AgentState;
  onEdit: (path: string, value: unknown) => void;
}

const URGENCY_LABEL: Record<Urgency, string> = {
  now: "Right now",
  soon: "Within a few hours",
  scheduled: "Scheduled",
};

export function StateView({ state, onEdit }: Props) {
  return (
    <div className="space-y-3">
      <PatientCard state={state} onEdit={onEdit} />
      <SituationCard state={state} onEdit={onEdit} />
      <EmergencyContactCard state={state} onEdit={onEdit} />
      <InsuranceCard state={state} onEdit={onEdit} />
      <PreferencesCard state={state} onEdit={onEdit} />
    </div>
  );
}

function Card({
  title,
  empty,
  children,
}: {
  title: string;
  empty?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      className={`rounded-2xl border bg-white dark:bg-zinc-900 dark:border-zinc-800 px-5 py-4 shadow-sm transition-colors ${
        empty ? "opacity-60" : ""
      }`}
    >
      <h3 className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
        {title}
      </h3>
      {children}
    </section>
  );
}

function EditableField({
  label,
  value,
  placeholder,
  onCommit,
  inputType = "text",
  required = false,
}: {
  label: string;
  value: string | number | undefined;
  placeholder?: string;
  onCommit: (next: string) => void;
  inputType?: "text" | "number" | "tel";
  required?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value == null ? "" : String(value));

  if (editing) {
    return (
      <label className="flex items-center gap-2 text-sm">
        <span className="w-28 text-zinc-500">{label}</span>
        <input
          autoFocus
          type={inputType}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => {
            setEditing(false);
            if (draft && draft !== String(value ?? "")) onCommit(draft);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            if (e.key === "Escape") {
              setDraft(String(value ?? ""));
              setEditing(false);
            }
          }}
          className="flex-1 rounded-md border border-zinc-300 dark:border-zinc-700 bg-transparent px-2 py-1 outline-none focus:ring-2 focus:ring-emerald-500/30"
        />
      </label>
    );
  }

  const unset = value == null || value === "";
  return (
    <button
      onClick={() => {
        setDraft(value == null ? "" : String(value));
        setEditing(true);
      }}
      className="flex items-center gap-2 text-sm w-full text-left rounded-md px-1 -mx-1 py-0.5 hover:bg-zinc-100 dark:hover:bg-zinc-800/50"
    >
      <span className="w-28 text-zinc-500">{label}</span>
      <span className={unset ? "text-zinc-400 italic flex-1" : "flex-1"}>
        {unset ? placeholder ?? "—" : String(value)}
      </span>
      {required && unset && <RequiredPill />}
    </button>
  );
}

function PatientCard({ state, onEdit }: Props) {
  const { patient } = state;
  const empty =
    patient.name == null && patient.age == null && patient.livesAlone == null;
  return (
    <Card title="Patient" empty={empty}>
      <div className="space-y-1">
        <EditableField
          label="Name"
          value={patient.name}
          placeholder="needed"
          required={!patient.name}
          onCommit={(v) => onEdit("patient.name", v)}
        />
        <EditableField
          label="Age"
          value={patient.age}
          placeholder="needed"
          required={patient.age == null}
          inputType="number"
          onCommit={(v) => {
            const n = Number(v);
            if (!Number.isNaN(n)) onEdit("patient.age", n);
          }}
        />
        <div className="flex items-center gap-2 text-sm">
          <span className="w-28 text-zinc-500">Lives alone</span>
          <ToggleChip
            value={patient.livesAlone === true}
            label="Yes"
            onClick={() => onEdit("patient.livesAlone", true)}
            active={patient.livesAlone === true}
          />
          <ToggleChip
            value={patient.livesAlone === false}
            label="No"
            onClick={() => onEdit("patient.livesAlone", false)}
            active={patient.livesAlone === false}
          />
          {patient.livesAlone == null && <RequiredPill />}
        </div>
      </div>
    </Card>
  );
}

function EmergencyContactCard({ state, onEdit }: Props) {
  const ec = state.emergencyContact;
  const empty = !ec.name && !ec.phone && !ec.relationship;
  return (
    <Card title="Emergency contact" empty={empty}>
      <div className="space-y-1">
        <EditableField
          label="Name"
          value={ec.name}
          placeholder="needed"
          required={!ec.name}
          onCommit={(v) => onEdit("emergencyContact.name", v)}
        />
        <EditableField
          label="Phone"
          value={ec.phone}
          placeholder="needed"
          required={!ec.phone}
          inputType="tel"
          onCommit={(v) => onEdit("emergencyContact.phone", v)}
        />
        <EditableField
          label="Relationship"
          value={ec.relationship}
          placeholder="optional (e.g. daughter)"
          onCommit={(v) => onEdit("emergencyContact.relationship", v)}
        />
      </div>
    </Card>
  );
}

function InsuranceCard({ state, onEdit }: Props) {
  const ins = state.insurance;
  const empty = !ins.provider && !ins.memberId;
  return (
    <Card title="Insurance" empty={empty}>
      <div className="space-y-1">
        <EditableField
          label="Provider"
          value={ins.provider}
          placeholder="needed (e.g. Medicare, Kaiser)"
          required={!ins.provider}
          onCommit={(v) => onEdit("insurance.provider", v)}
        />
        <EditableField
          label="Member ID"
          value={ins.memberId}
          placeholder="optional"
          onCommit={(v) => onEdit("insurance.memberId", v)}
        />
      </div>
    </Card>
  );
}

function RequiredPill() {
  return (
    <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
      needed
    </span>
  );
}

function SituationCard({ state, onEdit }: Props) {
  const { situation } = state;
  const empty =
    situation.description == null &&
    situation.issueTags.length === 0 &&
    situation.urgency == null;
  return (
    <Card title="Situation" empty={empty}>
      <div className="space-y-2">
        <EditableField
          label="Description"
          value={situation.description ?? undefined}
          placeholder="waiting…"
          onCommit={(v) => onEdit("situation.description", v)}
        />
        <div className="flex flex-wrap gap-1.5 pt-1">
          {situation.issueTags.length === 0 ? (
            <span className="text-xs text-zinc-400 italic">no tags yet</span>
          ) : (
            situation.issueTags.map((t) => (
              <span
                key={t}
                className="px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 text-xs"
              >
                {t}
              </span>
            ))
          )}
        </div>
        <div className="flex items-center gap-2 text-sm pt-1">
          <span className="w-28 text-zinc-500">Urgency</span>
          {(["now", "soon", "scheduled"] as const).map((u) => (
            <ToggleChip
              key={u}
              label={URGENCY_LABEL[u]}
              onClick={() => onEdit("situation.urgency", u)}
              active={situation.urgency === u}
            />
          ))}
        </div>
      </div>
    </Card>
  );
}

function PreferencesCard({ state, onEdit }: Props) {
  const { preferences } = state;
  const empty = !preferences.language && !preferences.genderPref;
  return (
    <Card title="Preferences" empty={empty}>
      <div className="space-y-1">
        <EditableField
          label="Language"
          value={preferences.language}
          placeholder="any"
          onCommit={(v) => onEdit("preferences.language", v)}
        />
        <div className="flex items-center gap-2 text-sm">
          <span className="w-28 text-zinc-500">Gender</span>
          <ToggleChip
            label="Any"
            onClick={() => onEdit("preferences.genderPref", null)}
            active={!preferences.genderPref}
          />
          <ToggleChip
            label="Female"
            onClick={() => onEdit("preferences.genderPref", "f")}
            active={preferences.genderPref === "f"}
          />
          <ToggleChip
            label="Male"
            onClick={() => onEdit("preferences.genderPref", "m")}
            active={preferences.genderPref === "m"}
          />
        </div>
      </div>
    </Card>
  );
}

function ToggleChip({
  label,
  onClick,
  active,
}: {
  label: string;
  value?: boolean;
  onClick: () => void;
  active: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-2.5 py-0.5 rounded-full text-xs border transition-colors ${
        active
          ? "bg-black text-white border-black dark:bg-white dark:text-black dark:border-white"
          : "bg-transparent text-zinc-600 dark:text-zinc-300 border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800"
      }`}
    >
      {label}
    </button>
  );
}
