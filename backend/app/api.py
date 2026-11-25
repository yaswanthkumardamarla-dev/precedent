"""Read-only JSON API for the dashboard, plus changing a decision's status."""
from typing import Literal

import hmac

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

from app import config



def require_token(authorization: str | None = Header(None)) -> None:
    """Only the dashboard's server, which holds API_TOKEN, may use this API."""
    if not config.API_TOKEN:
        raise HTTPException(status_code=503, detail="API_TOKEN is not configured on the server")
    expected = f"Bearer {config.API_TOKEN}"
    if not authorization or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid API token")


router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])

DecisionStatus = Literal["proposed", "accepted", "retired"]


def _query(sql: str, params: tuple = ()) -> list[dict]:
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()


@router.get("/summary")
def summary():
    """Headline counts for the dashboard."""
    by_status = {r["status"]: r["count"] for r in _query(
        "SELECT status, count(*) AS count FROM decisions GROUP BY status"
    )}
    [conflicts] = _query(
        "SELECT count(*) AS total, count(DISTINCT (repo, pr_number)) AS prs FROM conflicts"
    )
    [jobs] = _query(
        """
        SELECT count(*) FILTER (WHERE status = 'failed') AS failed,
               count(*) FILTER (WHERE status = 'queued') AS queued
        FROM webhook_events
        WHERE received_at > now() - interval '7 days'
        """
    )
    repos = [r["repo"] for r in _query("SELECT DISTINCT repo FROM decisions ORDER BY repo")]
    return {
        "decisions": {s: by_status.get(s, 0) for s in ("proposed", "accepted", "retired")},
        "conflicts": conflicts["total"],
        "prs_with_conflicts": conflicts["prs"],
        "failed_jobs_7d": jobs["failed"],
        "queued_jobs": jobs["queued"],
        "repos": repos,
    }


@router.get("/decisions")
def list_decisions(repo: str | None = None, status: DecisionStatus | None = None, q: str | None = None):
    """Decisions, newest first, with how many open conflicts cite each one."""
    return _query(
        """
        SELECT d.id, d.repo, d.pr_number, d.statement, d.rationale, d.scope,
               d.source_url, d.author, d.confidence, d.status, d.created_at,
               count(c.id) AS conflict_count
        FROM decisions d
        LEFT JOIN conflicts c ON c.decision_id = d.id
        WHERE (%(repo)s::text IS NULL OR d.repo = %(repo)s)
          AND (%(status)s::text IS NULL OR d.status = %(status)s)
          AND (%(q)s::text IS NULL OR d.statement ILIKE '%%' || %(q)s || '%%'
                                   OR d.rationale ILIKE '%%' || %(q)s || '%%')
        GROUP BY d.id
        ORDER BY d.created_at DESC
        LIMIT 500
        """,
        {"repo": repo, "status": status, "q": q or None},
    )


class StatusChange(BaseModel):
    status: DecisionStatus


@router.patch("/decisions/{decision_id}")
def set_decision_status(decision_id: int, change: StatusChange):
    """Accept a decision (kept when its PR is re-extracted) or retire it (no longer flagged)."""
    rows = _query(
        "UPDATE decisions SET status = %s WHERE id = %s RETURNING id, status",
        (change.status, decision_id),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No such decision")
    return rows[0]


@router.get("/conflicts")
def list_conflicts(repo: str | None = None):
    """Flagged PRs, each conflict with the decision it goes against."""
    return _query(
        """
        SELECT c.id, c.repo, c.pr_number, c.explanation, c.evidence, c.confidence, c.created_at,
               d.id AS decision_id, d.statement AS decision_statement,
               d.status AS decision_status, d.source_url AS decision_url,
               d.pr_number AS decision_pr_number
        FROM conflicts c
        JOIN decisions d ON d.id = c.decision_id
        WHERE (%(repo)s::text IS NULL OR c.repo = %(repo)s)
        ORDER BY c.created_at DESC
        LIMIT 500
        """,
        {"repo": repo},
    )


@router.get("/events")
def list_events(limit: int = 50):
    """Recent webhook deliveries and what Precedent did with them (without the raw payload)."""
    return _query(
        """
        SELECT id, delivery_id, event, action, repo, job, status, error, received_at, finished_at,
               COALESCE(payload->'pull_request'->>'number', payload->'issue'->>'number')::int AS pr_number
        FROM webhook_events
        ORDER BY received_at DESC
        LIMIT %s
        """,
        (min(max(limit, 1), 200),),
    )
