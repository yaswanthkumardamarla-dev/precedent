import type { ReactNode } from "react";

import type { DecisionStatus } from "@/lib/api";

const STATUS_STYLES: Record<string, string> = {
  proposed: "bg-amber-50 text-amber-800 ring-amber-600/20 dark:bg-amber-400/10 dark:text-amber-300",
  accepted: "bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-400/10 dark:text-emerald-300",
  retired: "bg-zinc-100 text-zinc-600 ring-zinc-500/20 dark:bg-zinc-400/10 dark:text-zinc-400",
  done: "bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-400/10 dark:text-emerald-300",
  failed: "bg-red-50 text-red-800 ring-red-600/20 dark:bg-red-400/10 dark:text-red-300",
  queued: "bg-sky-50 text-sky-800 ring-sky-600/20 dark:bg-sky-400/10 dark:text-sky-300",
  running: "bg-sky-50 text-sky-800 ring-sky-600/20 dark:bg-sky-400/10 dark:text-sky-300",
  ignored: "bg-zinc-100 text-zinc-500 ring-zinc-500/20 dark:bg-zinc-400/10 dark:text-zinc-500",
  skipped: "bg-zinc-100 text-zinc-500 ring-zinc-500/20 dark:bg-zinc-400/10 dark:text-zinc-500",
  limited: "bg-amber-50 text-amber-800 ring-amber-600/20 dark:bg-amber-400/10 dark:text-amber-300",
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

const GITHUB_MARK =
  "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z";

const BUTTON_VARIANTS = {
  solid: "bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300",
  outline:
    "border border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800",
};

/** A link-button with the GitHub mark, for signing in and installing the App. */
export function GitHubButton({
  href,
  children,
  size = "md",
  variant = "solid",
  className = "",
}: {
  href: string;
  children: ReactNode;
  size?: "sm" | "md";
  variant?: keyof typeof BUTTON_VARIANTS;
  className?: string;
}) {
  return (
    <a
      href={href}
      className={`inline-flex shrink-0 items-center gap-2 rounded-md font-medium ${BUTTON_VARIANTS[variant]} ${
        size === "sm" ? "px-3 py-1.5 text-sm" : "px-4 py-2 text-sm"
      } ${className}`}
    >
      <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true">
        <path d={GITHUB_MARK} />
      </svg>
      {children}
    </a>
  );
}
