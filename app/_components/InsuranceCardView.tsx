"use client";

import { Card, EditableField } from "./StateView";
import type { Insurance } from "../lib/types";

interface Props {
  insurance: Insurance;
  onEdit: (path: string, value: unknown) => void;
}

export function InsuranceCardView({ insurance, onEdit }: Props) {
  const empty =
    !insurance.insurer &&
    !insurance.memberId &&
    !insurance.groupNumber &&
    !insurance.planType;
  return (
    <Card title="Insurance" empty={empty}>
      <div className="space-y-1">
        <EditableField
          label="Carrier"
          value={insurance.insurer}
          placeholder="not on file"
          onCommit={(v) => onEdit("insurance.insurer", v)}
        />
        <EditableField
          label="Member ID"
          value={insurance.memberId}
          placeholder="—"
          onCommit={(v) => onEdit("insurance.memberId", v)}
        />
        <EditableField
          label="Group #"
          value={insurance.groupNumber}
          placeholder="—"
          onCommit={(v) => onEdit("insurance.groupNumber", v)}
        />
        <EditableField
          label="Plan"
          value={insurance.planType}
          placeholder="—"
          onCommit={(v) => onEdit("insurance.planType", v)}
        />
      </div>
    </Card>
  );
}
