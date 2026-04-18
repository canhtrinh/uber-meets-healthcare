"use client";

import { useState } from "react";
import type { AgentState, Urgency } from "../lib/types";

interface Props {
  state: AgentState;
  onEdit: (path: string, value: unknown) => void;
}

const URGENCY_LABEL: Record<Urgency, string> = {
  now: "Now",
  soon: "Soon",
  scheduled: "Later",
};

export function StateView({ state, onEdit }: Props) {
  return (
    <div className="space-y-2">
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
  filled,
  total,
  children,
  optional,
}: {
  title: string;
  filled: number;
  total: number;
  children: React.ReactNode;
  optional?: boolean;
}) {
  const complete = total > 0 && filled >= total;
  const empty = filled === 0;
  return (
    <section
      className={`rounded-xl border bg-white dark:bg-zinc-900 dark:border-zinc-800 px-3 py-2 shadow-sm transition-colors ${
        empty && !optional ? "border-dashed" : ""
      }`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
          {title}
          {optional && (
            <span className="ml-1 normal-case tracking-normal text-zinc-400 font-normal">
              · optional
            </span>
          )}
        </h3>
        {total > 0 && (
          <span
            className={`text-[10px] font-medium tabular-nums ${
              complete
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-zinc-400"
            }`}
          >
            {complete ? "✓ complete" : `${filled}/${total}`}
          </span>
        )}
      </div>
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
  labelWidth = "w-20",
}: {
  label: string;
  value: string | number | undefined;
  placeholder?: string;
  onCommit: (next: string) => void;
  inputType?: "text" | "number" | "tel";
  required?: boolean;
  labelWidth?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value == null ? "" : String(value));

  if (editing) {
    return (
      <label className="flex items-center gap-2 text-sm">
        <span className={`${labelWidth} text-[11px] text-zinc-500 shrink-0`}>
          {label}
        </span>
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
          className="flex-1 rounded-md border border-zinc-300 dark:border-zinc-700 bg-transparent px-2 py-0.5 text-sm outline-none focus:ring-2 focus:ring-emerald-500/30"
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
      <span className={`${labelWidth} text-[11px] text-zinc-500 shrink-0`}>
        {label}
      </span>
      <span
        className={
          unset
            ? "text-zinc-400 italic flex-1 truncate text-[13px]"
            : "flex-1 truncate text-[13px] font-medium"
        }
      >
        {unset ? placeholder ?? "—" : String(value)}
      </span>
      {required && unset && <RequiredPill />}
    </button>
  );
}

function PatientCard({ state, onEdit }: Props) {
  const { patient } = state;
  const filled =
    (patient.name ? 1 : 0) +
    (patient.age != null ? 1 : 0) +
    (patient.livesAlone != null ? 1 : 0);
  return (
    <Card title="Patient" filled={filled} total={3}>
      <div className="space-y-0.5">
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
          <span className="w-20 text-[11px] text-zinc-500 shrink-0">
            Alone
          </span>
          <ToggleChip
            label="Yes"
            onClick={() => onEdit("patient.livesAlone", true)}
            active={patient.livesAlone === true}
          />
          <ToggleChip
            label="No"
            onClick={() => onEdit("patient.livesAlone", false)}
            active={patient.livesAlone === false}
          />
          {patient.livesAlone == null && (
            <span className="ml-auto">
              <RequiredPill />
            </span>
          )}
        </div>
      </div>
    </Card>
  );
}

function SituationCard({ state, onEdit }: Props) {
  const { situation } = state;
  const filled =
    (situation.description ? 1 : 0) +
    (situation.issueTags.length > 0 ? 1 : 0) +
    (situation.urgency ? 1 : 0);
  return (
    <Card title="Situation" filled={filled} total={3}>
      <div className="space-y-1">
        <EditableField
          label="What"
          value={situation.description ?? undefined}
          placeholder="waiting…"
          required={!situation.description}
          onCommit={(v) => onEdit("situation.description", v)}
        />
        <div className="flex items-center gap-2 text-sm">
          <span className="w-20 text-[11px] text-zinc-500 shrink-0">Tags</span>
          <div className="flex flex-wrap gap-1 flex-1 min-w-0">
            {situation.issueTags.length === 0 ? (
              <span className="text-[11px] text-zinc-400 italic">
                waiting…
              </span>
            ) : (
              situation.issueTags.map((t) => (
                <span
                  key={t}
                  className="px-1.5 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 text-[11px]"
                >
                  {t}
                </span>
              ))
            )}
          </div>
          {situation.issueTags.length === 0 && <RequiredPill />}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="w-20 text-[11px] text-zinc-500 shrink-0">
            Urgency
          </span>
          {(["now", "soon", "scheduled"] as const).map((u) => (
            <ToggleChip
              key={u}
              label={URGENCY_LABEL[u]}
              onClick={() => onEdit("situation.urgency", u)}
              active={situation.urgency === u}
            />
          ))}
          {!situation.urgency && (
            <span className="ml-auto">
              <RequiredPill />
            </span>
          )}
        </div>
      </div>
    </Card>
  );
}

function EmergencyContactCard({ state, onEdit }: Props) {
  const ec = state.emergencyContact;
  const filled = (ec.name ? 1 : 0) + (ec.phone ? 1 : 0);
  return (
    <Card title="Emergency contact" filled={filled} total={2}>
      <div className="space-y-0.5">
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
          label="Relation"
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
  const filled = ins.provider ? 1 : 0;
  return (
    <Card title="Insurance" filled={filled} total={1}>
      <div className="space-y-0.5">
        <EditableField
          label="Provider"
          value={ins.provider}
          placeholder="needed (Medicare, Kaiser…)"
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

function PreferencesCard({ state, onEdit }: Props) {
  const { preferences } = state;
  const filled =
    (preferences.language ? 1 : 0) + (preferences.genderPref ? 1 : 0);
  return (
    <Card title="Preferences" filled={filled} total={0} optional>
      <div className="space-y-0.5">
        <EditableField
          label="Language"
          value={preferences.language}
          placeholder="any"
          onCommit={(v) => onEdit("preferences.language", v)}
        />
        <div className="flex items-center gap-2 text-sm">
          <span className="w-20 text-[11px] text-zinc-500 shrink-0">
            Gender
          </span>
          <ToggleChip
            label="Any"
            onClick={() => onEdit("preferences.genderPref", null)}
            active={!preferences.genderPref}
          />
          <ToggleChip
            label="F"
            onClick={() => onEdit("preferences.genderPref", "f")}
            active={preferences.genderPref === "f"}
          />
          <ToggleChip
            label="M"
            onClick={() => onEdit("preferences.genderPref", "m")}
            active={preferences.genderPref === "m"}
          />
        </div>
      </div>
    </Card>
  );
}

function RequiredPill() {
  return (
    <span className="shrink-0 text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
      needed
    </span>
  );
}

function ToggleChip({
  label,
  onClick,
  active,
}: {
  label: string;
  onClick: () => void;
  active: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-2 py-0.5 rounded-full text-[11px] border transition-colors ${
        active
          ? "bg-black text-white border-black dark:bg-white dark:text-black dark:border-white"
          : "bg-transparent text-zinc-600 dark:text-zinc-300 border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800"
      }`}
    >
      {label}
    </button>
  );
}
