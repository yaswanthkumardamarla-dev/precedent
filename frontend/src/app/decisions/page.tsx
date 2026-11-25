import Link from "next/link";
import { Suspense } from "react";

import { DecisionActions } from "@/components/decision-actions";
import { Badge, Card, Empty, ExternalLink, Loading } from "@/components/ui";
import { DECISION_STATUSES, type DecisionStatus, formatDate, getDecisions, prUrl } from "@/lib/api";

type Filters = { status?: DecisionStatus; q?: string };

function parseFilters(params: Record<string, string | string[] | undefined>): Filters {
  const status = typeof params.status === "string" ? params.status : undefined;
  const q = typeof params.q === "string" ? params.q.trim() : undefined;
  return {
    status: DECISION_STATUSES.includes(status as DecisionStatus) ? (status as DecisionStatus) : undefined,
    q: q || undefined,
  };
}

export default function DecisionsPage({ searchParams }: PageProps<"/decisions">) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Decisions</h1>
        <p className="text-sm text-zinc-500">
          Rules extracted from review discussions. Accepted decisions are kept when a PR is re-extracted; retired
          ones are no longer flagged.
        </p>
      </div>
      <Suspense fallback={<Loading />}>
        <FilteredDecisions searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function FilteredDecisions({ searchParams }: { searchParams: PageProps<"/decisions">["searchParams"] }) {
  const filters = parseFilters(await searchParams);
  const decisions = await getDecisions(filters);

  return (
    <>
      <FilterBar filters={filters} />
      {decisions.length === 0 ? (
        <Empty>
          {filters.status || filters.q
            ? "No decisions match these filters."
            : "No decisions yet. They are extracted when review comments are posted or a PR is closed."}
        </Empty>
      ) : (
        <ul className="space-y-3">
          {decisions.map((d) => (
            <li key={d.id}>
              <Card>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge status={d.status} />
                      {d.conflict_count > 0 && (
                        <span className="text-xs font-medium text-red-700 dark:text-red-400">
                          {d.conflict_count} conflict{d.conflict_count === 1 ? "" : "s"}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 font-medium">{d.statement}</p>
                    {d.rationale && <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">Why: {d.rationale}</p>}
                    {d.scope && <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">Applies to: {d.scope}</p>}
                    <p className="mt-2 text-xs text-zinc-500">
                      <ExternalLink href={d.source_url}>Source comment</ExternalLink>
                      {d.author && <> by {d.author}</>} in{" "}
                      <ExternalLink href={prUrl(d.repo, d.pr_number)}>
                        {d.repo} #{d.pr_number}
                      </ExternalLink>{" "}
                      · {formatDate(d.created_at)}
                      {d.confidence != null && <> · confidence {Math.round(d.confidence * 100)}%</>}
                    </p>
                  </div>
                  {d.can_edit && <DecisionActions id={d.id} status={d.status} />}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function FilterBar({ filters }: { filters: Filters }) {
  const tabs: { label: string; status?: DecisionStatus }[] = [
    { label: "All" },
    ...DECISION_STATUSES.map((s) => ({ label: s[0].toUpperCase() + s.slice(1), status: s })),
  ];
  const href = (status?: DecisionStatus) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (filters.q) params.set("q", filters.q);
    const text = params.toString();
    return text ? `/decisions?${text}` : "/decisions";
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex gap-1">
        {tabs.map((t) => (
          <Link
            key={t.label}
            href={href(t.status)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              filters.status === t.status
                ? "bg-zinc-200 font-medium dark:bg-zinc-800"
                : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
            }`}
          >
            {t.label}
          </Link>
        ))}
      </div>
      <form action="/decisions" className="flex gap-2">
        {filters.status && <input type="hidden" name="status" value={filters.status} />}
        <input
          name="q"
          defaultValue={filters.q}
          placeholder="Search decisions…"
          className="w-64 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />
        <button type="submit" className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700">
          Search
        </button>
      </form>
    </div>
  );
}
