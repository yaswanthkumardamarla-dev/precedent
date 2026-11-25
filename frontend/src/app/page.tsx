import Link from "next/link";
import { Suspense } from "react";

import { Badge, Card, Empty, ExternalLink, Loading } from "@/components/ui";
import { type Conflict, formatDate, getConflicts, getSummary, prUrl } from "@/lib/api";

export default function Overview() {
  return (
    <div className="space-y-10">
      <Suspense fallback={<Loading />}>
        <Stats />
      </Suspense>
      <section>
        <h2 className="mb-1 text-lg font-semibold">Flagged pull requests</h2>
        <p className="mb-4 text-sm text-zinc-500">
          Open PRs whose changes may go against a decision made in an earlier review.
        </p>
        <Suspense fallback={<Loading label="Loading conflicts…" />}>
          <FlaggedPRs />
        </Suspense>
      </section>
    </div>
  );
}

async function Stats() {
  const s = await getSummary();
  const stats = [
    { label: "Proposed decisions", value: s.decisions.proposed, href: "/decisions?status=proposed", hint: "awaiting review" },
    { label: "Accepted decisions", value: s.decisions.accepted, href: "/decisions?status=accepted", hint: "enforced" },
    { label: "Conflicts", value: s.conflicts, href: "#flagged", hint: `across ${s.prs_with_conflicts} PR(s)` },
    {
      label: "Failed jobs",
      value: s.failed_jobs_7d,
      href: "/activity",
      hint: s.queued_jobs ? `${s.queued_jobs} queued` : "last 7 days",
    },
  ];
  return (
    <div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {stats.map((stat) => (
          <Link key={stat.label} href={stat.href}>
            <Card className="h-full transition-colors hover:border-zinc-400 dark:hover:border-zinc-600">
              <div className="text-sm text-zinc-500">{stat.label}</div>
              <div className="mt-1 text-3xl font-semibold tabular-nums">{stat.value}</div>
              <div className="mt-1 text-xs text-zinc-400">{stat.hint}</div>
            </Card>
          </Link>
        ))}
      </div>
      {s.repos.length > 0 && (
        <p className="mt-3 text-xs text-zinc-500">Watching: {s.repos.join(", ")}</p>
      )}
    </div>
  );
}

async function FlaggedPRs() {
  const conflicts = await getConflicts();
  if (conflicts.length === 0) {
    return <Empty>No conflicts. New PRs are checked automatically when they are opened or updated.</Empty>;
  }

  const byPr = new Map<string, Conflict[]>();
  for (const c of conflicts) {
    const key = `${c.repo}#${c.pr_number}`;
    byPr.set(key, [...(byPr.get(key) ?? []), c]);
  }

  return (
    <div id="flagged" className="space-y-4">
      {[...byPr.entries()].map(([key, items]) => {
        const { repo, pr_number, created_at } = items[0];
        return (
          <Card key={key}>
            <div className="mb-3 flex items-baseline justify-between gap-4">
              <ExternalLink href={prUrl(repo, pr_number)}>
                <span className="font-medium">
                  {repo} #{pr_number}
                </span>
              </ExternalLink>
              <span className="text-xs text-zinc-400">checked {formatDate(created_at)}</span>
            </div>
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {items.map((c) => (
                <li key={c.id} className="py-3 first:pt-0 last:pb-0">
                  <div className="flex items-start justify-between gap-4">
                    <p className="font-medium">{c.decision_statement}</p>
                    {c.decision_status === "retired" && <Badge status="retired" />}
                  </div>
                  <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{c.explanation}</p>
                  {c.evidence && (
                    <pre className="mt-2 overflow-x-auto rounded bg-zinc-100 px-2 py-1 font-mono text-xs dark:bg-zinc-800">
                      {c.evidence}
                    </pre>
                  )}
                  <p className="mt-2 text-xs text-zinc-500">
                    Decided in <ExternalLink href={c.decision_url}>PR #{c.decision_pr_number}</ExternalLink>
                    {c.confidence != null && <> · confidence {Math.round(c.confidence * 100)}%</>}
                  </p>
                </li>
              ))}
            </ul>
          </Card>
        );
      })}
    </div>
  );
}
