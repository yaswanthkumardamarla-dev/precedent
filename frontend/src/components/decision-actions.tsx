"use client";

import { useFormStatus } from "react-dom";

import { setDecisionStatus } from "@/app/actions";
import type { DecisionStatus } from "@/lib/api";

const ACTIONS: Record<DecisionStatus, { to: DecisionStatus; label: string; primary?: boolean }[]> = {
  proposed: [
    { to: "accepted", label: "Accept", primary: true },
    { to: "retired", label: "Retire" },
  ],
  accepted: [{ to: "retired", label: "Retire" }],
  retired: [{ to: "accepted", label: "Reinstate" }],
};

function ActionButton({ to, label, primary }: { to: DecisionStatus; label: string; primary?: boolean }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      name="status"
      value={to}
      disabled={pending}
      className={`rounded-md px-2.5 py-1 text-xs font-medium disabled:opacity-50 ${
        primary
          ? "bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          : "border border-zinc-300 text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
      }`}
    >
      {label}
    </button>
  );
}

export function DecisionActions({ id, status }: { id: number; status: DecisionStatus }) {
  return (
    <form action={setDecisionStatus} className="flex shrink-0 gap-2">
      <input type="hidden" name="id" value={id} />
      {ACTIONS[status].map((a) => (
        <ActionButton key={a.to} {...a} />
      ))}
    </form>
  );
}
