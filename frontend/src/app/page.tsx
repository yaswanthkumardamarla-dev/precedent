import Link from "next/link";
import { Suspense } from "react";

import { Badge, Card, Empty, ExternalLink, GitHubButton, Loading } from "@/components/ui";
import { type Conflict, type Me, formatDate, getConflicts, getMe, getSummary, prUrl } from "@/lib/api";

export default function Overview({ searchParams }: PageProps<"/">) {
  return (
    <Suspense fallback={<Loading />}>
      <OverviewBody searchParams={searchParams} />
    </Suspense>
  );
}

async function OverviewBody({ searchParams }: { searchParams: PageProps<"/">["searchParams"] }) {
  // GitHub sends people back with ?installed=1 after they install Precedent: re-read their repositories.
  const me = await getMe((await searchParams).installed === "1");
  return (
    <div className="space-y-10">
      <Intro me={me} />
      {me.repos.length > 0 && (
        <>
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
        </>
      )}
    </div>
  );
}

const repoLink = (name: string) => <ExternalLink href={`https://github.com/${name}`}>{name}</ExternalLink>;

function Intro({ me }: { me: Me }) {
  const limits = `Free demo: public repositories only, up to ${me.limits.repo_daily_jobs} checks per repository per day.`;

  if (me.demo) {
    return (
      <Card className="p-6">
        <h1 className="text-xl font-semibold tracking-tight">Decision memory for pull requests</h1>
        <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
          Teams make decisions in code review (&ldquo;always use the logging module&rdquo;, &ldquo;every endpoint
          needs type hints&rdquo;) and then forget them. Precedent reads review discussions, extracts those
          decisions with an LLM, and comments on new pull requests that go against one, linking back to where it
          was decided.
        </p>
        {me.repos.length > 0 && (
          <p className="mt-3 text-sm text-zinc-500">
            Below is a live, read-only demo on {me.repos.map((r) => repoLink(r.name))}.
          </p>
        )}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <GitHubButton href="/auth/signin">Sign in with GitHub to try it on your repositories</GitHubButton>
          <span className="text-xs text-zinc-500">{limits}</span>
        </div>
      </Card>
    );
  }

  if (me.repos.length === 0) {
    return (
      <Card className="p-6">
        <h1 className="text-xl font-semibold tracking-tight">Welcome, {me.login}</h1>
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">Three steps to see Precedent work on your own code:</p>
        <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-zinc-600 dark:text-zinc-400">
          <li>Install Precedent on one or more public repositories.</li>
          <li>
            In a pull request review, state a rule, for example: &ldquo;Let&apos;s always use the logging module
            instead of print.&rdquo;
          </li>
          <li>Open another pull request that breaks it. Precedent comments within a minute or two.</li>
        </ol>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <GitHubButton href={me.install_url}>Install Precedent on GitHub</GitHubButton>
          <span className="text-xs text-zinc-500">{limits}</span>
        </div>
      </Card>
    );
  }

  const privateRepos = me.repos.filter((r) => r.private);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Watching {me.repos.length} {me.repos.length === 1 ? "repository" : "repositories"}:{" "}
        {me.repos.map((r, i) => (
          <span key={r.name}>
            {i > 0 && ", "}
            {repoLink(r.name)}
            {r.private && " (private, not checked)"}
          </span>
        ))}
        {privateRepos.length > 0 && ". Private repositories are not checked in this free demo"}
      </p>
      <a href={me.install_url} className="text-sm text-sky-700 hover:underline dark:text-sky-400">
        Add or remove repositories
      </a>
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
      hint: s.queued_jobs ? `${s.queued_jobs} in progress` : "last 7 days",
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
