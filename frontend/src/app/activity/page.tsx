import { Suspense } from "react";

import { Badge, Card, Empty, ExternalLink, Loading } from "@/components/ui";
import { formatDate, getEvents, prUrl } from "@/lib/api";

export default function ActivityPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Activity</h1>
        <p className="text-sm text-zinc-500">
          The latest GitHub webhook deliveries and what Precedent did with each one.
        </p>
      </div>
      <Suspense fallback={<Loading />}>
        <Events />
      </Suspense>
    </div>
  );
}

const JOB_LABELS = { check: "Checked for conflicts", extract: "Extracted decisions" } as const;

function seconds(start: string, end: string | null) {
  if (!end) return null;
  return ((new Date(end).getTime() - new Date(start).getTime()) / 1000).toFixed(1);
}

async function Events() {
  const events = await getEvents(100);
  if (events.length === 0) {
    return <Empty>No webhook deliveries yet. Check that the GitHub App&apos;s webhook points at this backend.</Empty>;
  }

  return (
    <Card className="overflow-x-auto p-0">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800">
          <tr>
            <th className="px-4 py-2 font-medium">Received</th>
            <th className="px-4 py-2 font-medium">Event</th>
            <th className="px-4 py-2 font-medium">Pull request</th>
            <th className="px-4 py-2 font-medium">Job</th>
            <th className="px-4 py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {events.map((e) => {
            const took = seconds(e.received_at, e.finished_at);
            return (
              <tr key={e.id} className="align-top">
                <td className="whitespace-nowrap px-4 py-2 text-zinc-500">{formatDate(e.received_at)}</td>
                <td className="px-4 py-2 font-mono text-xs">
                  {e.event}
                  {e.action && <span className="text-zinc-400"> · {e.action}</span>}
                </td>
                <td className="whitespace-nowrap px-4 py-2">
                  {e.repo && e.pr_number ? (
                    <ExternalLink href={prUrl(e.repo, e.pr_number)}>
                      {e.repo.split("/")[1]} #{e.pr_number}
                    </ExternalLink>
                  ) : (
                    <span className="text-zinc-400">{e.repo ?? "—"}</span>
                  )}
                </td>
                <td className="px-4 py-2">{e.job ? JOB_LABELS[e.job] : <span className="text-zinc-400">—</span>}</td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-2">
                    <Badge status={e.status} />
                    {took && e.job && <span className="text-xs text-zinc-400">{took}s</span>}
                  </div>
                  {e.error && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs text-red-700 dark:text-red-400">Show error</summary>
                      <pre className="mt-1 max-w-xl overflow-x-auto whitespace-pre-wrap rounded bg-red-50 p-2 font-mono text-xs text-red-900 dark:bg-red-950 dark:text-red-200">
                        {e.error}
                      </pre>
                    </details>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
