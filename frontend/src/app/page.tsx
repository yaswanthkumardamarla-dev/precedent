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

  return <WatchedRepos me={me} />;
}

// GitHub's Octicons (MIT): repo and lock, 16px.
const REPO_ICON =
  "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.087a.25.25 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z";
const LOCK_ICON =
  "M4 4a4 4 0 0 1 8 0v2h.25c.966 0 1.75.784 1.75 1.75v5.5A1.75 1.75 0 0 1 12.25 15h-8.5A1.75 1.75 0 0 1 2 13.25v-5.5C2 6.784 2.784 6 3.75 6H4Zm8.25 3.5h-8.5a.25.25 0 0 0-.25.25v5.5c0 .138.112.25.25.25h8.5a.25.25 0 0 0 .25-.25v-5.5a.25.25 0 0 0-.25-.25ZM10.5 6V4a2.5 2.5 0 1 0-5 0v2Z";

const Icon = ({ path, className = "" }: { path: string; className?: string }) => (
  <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true" className={className}>
    <path d={path} />
  </svg>
);

/** The signed-in person's repositories: one row each, with whether Precedent checks it. */
function WatchedRepos({ me }: { me: Me }) {
  // Checked repositories first, then by name.
  const repos = [...me.repos].sort((a, b) => Number(a.private) - Number(b.private) || a.name.localeCompare(b.name));
  const checked = repos.filter((r) => !r.private).length;

  return (
    <Card className="p-0">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-5 pb-4">
        <div>
          <h1 className="text-base font-semibold tracking-tight">Your repositories</h1>
          <p className="mt-0.5 text-sm text-zinc-500">
            Checking new pull requests in {checked} of {repos.length}{" "}
            {repos.length === 1 ? "repository" : "repositories"}.
          </p>
        </div>
        <GitHubButton href={me.install_url} size="sm" variant="outline">
          Add or remove
        </GitHubButton>
      </div>

      <ul className="divide-y divide-zinc-100 border-y border-zinc-100 dark:divide-zinc-800 dark:border-zinc-800">
        {repos.map((r) => {
          const [owner, name] = r.name.split("/");
          return (
            <li key={r.name} className="flex items-center gap-3 px-5 py-3">
              <Icon path={r.private ? LOCK_ICON : REPO_ICON} className="shrink-0 text-zinc-400" />
              <a
                href={`https://github.com/${r.name}`}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 truncate text-sm hover:underline"
              >
                <span className="text-zinc-500">{owner}/</span>
                <span className="font-medium text-zinc-900 dark:text-zinc-100">{name}</span>
              </a>
              <div className="ml-auto flex shrink-0 items-center gap-2">
                {!r.can_write && (
                  <span className="hidden text-xs text-zinc-500 sm:inline" title="You can't accept or retire its decisions">
                    read-only
                  </span>
                )}
                {r.private ? (
                  <span
                    className="inline-flex items-center rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-600 ring-1 ring-zinc-500/20 ring-inset dark:bg-zinc-400/10 dark:text-zinc-400"
                    title="Private repositories are not checked in this free demo"
                  >
                    Private · not checked
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-800 ring-1 ring-emerald-600/20 ring-inset dark:bg-emerald-400/10 dark:text-emerald-300">
                    <span className="size-1.5 rounded-full bg-emerald-500" />
                    Checking PRs
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <p className="px-5 py-3 text-xs text-zinc-500">
        Free demo: up to {me.limits.repo_daily_jobs} checks per repository per day.
        {checked < repos.length &&
          " Private repositories are skipped, because pull request code is sent to a free AI tier that may learn from it."}
      </p>
    </Card>
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
