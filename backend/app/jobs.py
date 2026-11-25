"""Running webhook jobs (check a PR, or extract its decisions), and retrying the ones that failed."""
import traceback

import psycopg

from app import config
from app.check import check_pr
from app.extract import extract_pr

MAX_ATTEMPTS = 3  # including the first run
RETRY_WINDOW = "6 hours"  # older failures are left alone
STUCK_AFTER = "15 minutes"  # a job still queued/running this long was lost, e.g. in a restart


def _update(delivery_id: str, sql: str, params: tuple = ()) -> None:
    with psycopg.connect(config.DATABASE_URL) as conn:
        conn.execute(f"UPDATE webhook_events SET {sql} WHERE delivery_id = %s", (*params, delivery_id))


def run_job(delivery_id: str, job: str, repo: str, number: int) -> None:
    """Run one job and record how it went. Safe to repeat: each run works from the PR's current state."""
    _update(delivery_id, "status = 'running', attempts = attempts + 1, error = NULL, finished_at = NULL")
    print(f"[job] {job} {repo}#{number} starting", flush=True)
    try:
        if job == "check":
            check_pr(repo, number, post=True)
        else:
            extract_pr(repo, number)
        _update(delivery_id, "status = 'done', finished_at = now()")
        print(f"[job] {job} {repo}#{number} done", flush=True)
    except Exception:
        error = traceback.format_exc()
        print(f"[job] {job} {repo}#{number} FAILED\n{error}", flush=True)
        _update(delivery_id, "status = 'failed', error = %s, finished_at = now()", (error,))


def retry_failed_jobs() -> int:
    """Re-run recent jobs that failed or got stuck, unless a newer run of the same job on the same PR succeeded."""
    with psycopg.connect(config.DATABASE_URL) as conn:
        rows = conn.execute(
            f"""
            WITH events AS (
                SELECT *, COALESCE(payload->'pull_request'->>'number', payload->'issue'->>'number')::int AS pr_number
                FROM webhook_events
                WHERE job IS NOT NULL
            )
            SELECT e.delivery_id, e.job, e.repo, e.pr_number, e.attempts
            FROM events e
            WHERE e.attempts < %s
              AND e.received_at > now() - interval '{RETRY_WINDOW}'
              AND (e.status = 'failed'
                   OR (e.status IN ('queued', 'running') AND e.received_at < now() - interval '{STUCK_AFTER}'))
              AND NOT EXISTS (
                  SELECT 1 FROM events later
                  WHERE later.repo = e.repo AND later.pr_number = e.pr_number AND later.job = e.job
                    AND later.status = 'done' AND later.received_at > e.received_at
              )
            ORDER BY e.received_at
            """,
            (MAX_ATTEMPTS,),
        ).fetchall()
    # Several failed events for the same job on the same PR need only one run, since each run uses
    # the PR's current state. Run the newest; if it succeeds, the older ones are settled too.
    groups: dict[tuple, list] = {}
    for row in rows:
        groups.setdefault((row[1], row[2], row[3]), []).append(row)
    for (job, repo, number), group in groups.items():
        delivery_id, *_, attempts = group[-1]
        print(f"[retry] {job} {repo}#{number}: attempt {attempts + 1} of {MAX_ATTEMPTS}", flush=True)
        run_job(delivery_id, job, repo, number)
        with psycopg.connect(config.DATABASE_URL) as conn:
            succeeded = conn.execute(
                "SELECT status = 'done' FROM webhook_events WHERE delivery_id = %s", (delivery_id,)
            ).fetchone()[0]
            if succeeded:
                conn.execute(
                    "UPDATE webhook_events SET status = 'done', error = NULL, finished_at = now() "
                    "WHERE delivery_id = ANY(%s)",
                    ([older[0] for older in group[:-1]],),
                )
    return len(groups)
