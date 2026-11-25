"use server";

import { refresh } from "next/cache";

import { DECISION_STATUSES, type DecisionStatus, updateDecisionStatus } from "@/lib/api";

// The backend allows this only for people with write access to the decision's repository on GitHub.
export async function setDecisionStatus(formData: FormData) {
  const id = Number(formData.get("id"));
  const status = formData.get("status") as DecisionStatus;
  if (!Number.isInteger(id) || !DECISION_STATUSES.includes(status)) {
    throw new Error("Invalid decision status change");
  }
  await updateDecisionStatus(id, status);
  refresh();
}
