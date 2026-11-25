import type { ReactNode } from "react";

import type { DecisionStatus } from "@/lib/api";

const STATUS_STYLES: Record<string, string> = {
  proposed: "bg-amber-50 text-amber-800 ring-amber-600/20 dark:bg-amber-400/10 dark:text-amber-300",
  accepted: "bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-400/10 dark:text-emerald-300",
  retired: "bg-zinc-100 text-zinc-600 ring-zinc-500/20 dark:bg-zinc-400/10 dark:text-zinc-400",
  done: "bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-400/10 dark:text-emerald-300",
  failed: "bg-red-50 text-red-800 ring-red-600/20 dark:bg-red-400/10 dark:text-red-300",
  queued: "bg-sky-50 text-sky-800 ring-sky-600/20 dark:bg-sky-400/10 dark:text-sky-300",
  ignored: "bg-zinc-100 text-zinc-500 ring-zinc-500/20 dark:bg-zinc-400/10 dark:text-zinc-500",
};

export function Badge({ status }: { status: DecisionStatus | string | null }) {
  const label = status ?? "unknown";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
        STATUS_STYLES[label] ?? STATUS_STYLES.ignored
      }`}
    >
      {label}
    </span>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900 ${className}`}>
      {children}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700">
      {children}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="animate-pulse p-8 text-center text-sm text-zinc-400">{label}</div>;
}

export function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-sky-700 hover:underline dark:text-sky-400">
      {children}
    </a>
  );
}
