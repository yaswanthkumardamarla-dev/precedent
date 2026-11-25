// Server-side access to the Precedent FastAPI backend. Only import this from Server Components and Server Actions.
import { connection } from "next/server";

export const BACKEND_URL = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

export const DECISION_STATUSES = ["proposed", "accepted", "retired"] as const;
export type DecisionStatus = (typeof DECISION_STATUSES)[number];

export type Summary = {
  decisions: Record<DecisionStatus, number>;
  conflicts: number;
  prs_with_conflicts: number;
  failed_jobs_7d: number;
  queued_jobs: number;
  repos: string[];
};

export type Decision = {
  id: number;
  repo: string;
  pr_number: number;
  statement: string;
  rationale: string;
  scope: string;
  source_url: string;
  author: string | null;
  confidence: number | null;
  status: DecisionStatus;
  created_at: string;
  conflict_count: number;
};

export type Conflict = {
  id: number;
  repo: string;
  pr_number: number;
  explanation: string;
  evidence: string;
  confidence: number | null;
  created_at: string;
  decision_id: number;
  decision_statement: string;
  decision_status: DecisionStatus;
  decision_url: string;
  decision_pr_number: number;
};

export type WebhookEvent = {
  id: number;
  delivery_id: string;
  event: string;
  action: string | null;
  repo: string | null;
  job: "check" | "extract" | null;
  status: "queued" | "running" | "done" | "failed" | "ignored" | null;
  error: string | null;
  attempts: number;
  received_at: string;
  finished_at: string | null;
  pr_number: number | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  await connection(); // always live data, fetched per request; never at build time
  const token = process.env.BACKEND_API_TOKEN;
  if (!token) throw new Error("BACKEND_API_TOKEN is not set, so the dashboard can't call the backend.");
  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}${path}`, {
      cache: "no-store",
      ...init,
      headers: { ...init?.headers, Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new Error(`Can't reach the Precedent backend at ${BACKEND_URL}. Is it running?`);
  }
  if (!response.ok) {
    throw new Error(`Backend returned ${response.status} for ${path}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const getSummary = () => request<Summary>("/api/summary");

export const getDecisions = (filters: { repo?: string; status?: DecisionStatus; q?: string } = {}) =>
  request<Decision[]>(`/api/decisions${query(filters)}`);

export const getConflicts = (repo?: string) => request<Conflict[]>(`/api/conflicts${query({ repo })}`);

export const getEvents = (limit = 50) => request<WebhookEvent[]>(`/api/events?limit=${limit}`);

export const updateDecisionStatus = (id: number, status: DecisionStatus) =>
  request<{ id: number; status: DecisionStatus }>(`/api/decisions/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });

export const prUrl = (repo: string, number: number) => `https://github.com/${repo}/pull/${number}`;

const dateFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
export const formatDate = (iso: string) => dateFormat.format(new Date(iso));
