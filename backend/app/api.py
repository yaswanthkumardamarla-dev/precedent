"""JSON API for the dashboard. Every answer is limited to the repositories the viewer may see."""
import hmac
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

from app import config
from app.access import Viewer, current_viewer, viewer_for
from app.github_client import app_slug


def require_token(authorization: str | None = Header(None)) -> None:
    """Only the dashboard's server, which holds API_TOKEN, may use this API."""
    if not config.API_TOKEN:
        raise HTTPException(status_code=503, detail="API_TOKEN is not configured on the server")
    expected = f"Bearer {config.API_TOKEN}"
    if not authorization or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid API token")


router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])

DecisionStatus = Literal["proposed", "accepted", "retired"]


def _query(sql: str, params: dict | tuple = ()) -> list[dict]:
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()


@router.get("/me")
def me(refresh: bool = False, x_github_token: str | None = Header(None)):
    """Who is viewing, their repositories, and the demo's limits. refresh=true skips the cached repo list."""
    viewer = viewer_for(x_github_token, refresh=refresh)
    return {
        "login": viewer.login,
        "demo": viewer.is_demo,
        "repos": [{"name": r.name, "private": r.private, "can_write": r.can_write} for r in viewer.repos],
        "install_url": f"https://github.com/apps/{app_slug()}/installations/new",
        "limits": {
            "repo_daily_jobs": config.REPO_DAILY_JOB_LIMIT,
            "owner_daily_jobs": config.OWNER_DAILY_JOB_LIMIT,
        },
    }


@router.get("/summary")
def summary(viewer: Viewer = Depends(current_viewer)):
    """Headline counts for the dashboard."""
    repos = viewer.names
    by_status = {r["status"]: r["count"] for r in _query(
        "SELECT status, count(*) AS count FROM decisions WHERE repo = ANY(%s) GROUP BY status", (repos,)
    )}
    [conflicts] = _query(
        "SELECT count(*) AS total, count(DISTINCT (repo, pr_number)) AS prs FROM conflicts WHERE repo = ANY(%s)",
        (repos,),
    )
    [jobs] = _query(
        """
        SELECT count(*) FILTER (WHERE status = 'failed') AS failed,
               count(*) FILTER (WHERE status IN ('queued', 'running')) AS queued
        FROM webhook_events
        WHERE repo = ANY(%s) AND received_at > now() - interval '7 days'
        """,
        (repos,),
    )
    return {
        "decisions": {s: by_status.get(s, 0) for s in ("proposed", "accepted", "retired")},
        "conflicts": conflicts["total"],
        "prs_with_conflicts": conflicts["prs"],
        "failed_jobs_7d": jobs["failed"],
        "queued_jobs": jobs["queued"],
        "repos": repos,
    }


@router.get("/decisions")
def list_decisions(
    status: DecisionStatus | None = None, q: str | None = None, viewer: Viewer = Depends(current_viewer)
):
    """Decisions, newest first, with how many conflicts cite each one, and whether the viewer may change it."""
    rows = _query(
        """
        SELECT d.id, d.repo, d.pr_number, d.statement, d.rationale, d.scope,
               d.source_url, d.author, d.confidence, d.status, d.created_at,
               count(c.id) AS conflict_count
        FROM decisions d
        LEFT JOIN conflicts c ON c.decision_id = d.id
        WHERE d.repo = ANY(%(repos)s)
          AND (%(status)s::text IS NULL OR d.status = %(status)s)
          AND (%(q)s::text IS NULL OR d.statement ILIKE '%%' || %(q)s || '%%'
                                   OR d.rationale ILIKE '%%' || %(q)s || '%%')
        GROUP BY d.id
        ORDER BY d.created_at DESC
        LIMIT 500
        """,
        {"repos": viewer.names, "status": status, "q": q or None},
    )
    for row in rows:
        row["can_edit"] = viewer.can_write(row["repo"])
    return rows


class StatusChange(BaseModel):
    status: DecisionStatus


@router.patch("/decisions/{decision_id}")
def set_decision_status(decision_id: int, change: StatusChange, viewer: Viewer = Depends(current_viewer)):
    """Accept a decision (kept when its PR is re-extracted) or retire it (no longer flagged).

    Only people with write access to the decision's repository on GitHub may do this.
    """
    found = _query("SELECT repo FROM decisions WHERE id = %s AND repo = ANY(%s)", (decision_id, viewer.names))
    if not found:
        raise HTTPException(status_code=404, detail="No such decision")
    if not viewer.can_write(found[0]["repo"]):
        raise HTTPException(status_code=403, detail="You need write access to this repository on GitHub")
    return _query(
        "UPDATE decisions SET status = %s WHERE id = %s RETURNING id, status", (change.status, decision_id)
    )[0]


@router.get("/conflicts")
def list_conflicts(viewer: Viewer = Depends(current_viewer)):
    """Flagged PRs, each conflict with the decision it goes against."""
    return _query(
        """
        SELECT c.id, c.repo, c.pr_number, c.explanation, c.evidence, c.confidence, c.created_at,
               d.id AS decision_id, d.statement AS decision_statement,
               d.status AS decision_status, d.source_url AS decision_url,
               d.pr_number AS decision_pr_number
        FROM conflicts c
        JOIN decisions d ON d.id = c.decision_id
        WHERE c.repo = ANY(%s)
        ORDER BY c.created_at DESC
        LIMIT 500
        """,
        (viewer.names,),
    )


@router.get("/events")
def list_events(limit: int = 50, viewer: Viewer = Depends(current_viewer)):
    """Recent webhook deliveries and what Precedent did with them (without the raw payload)."""
    return _query(
        """
        SELECT id, delivery_id, event, action, repo, job, status, error, attempts, received_at, finished_at,
               COALESCE(payload->'pull_request'->>'number', payload->'issue'->>'number')::int AS pr_number
        FROM webhook_events
        WHERE repo = ANY(%s)
        ORDER BY received_at DESC
        LIMIT %s
        """,
        (viewer.names, min(max(limit, 1), 200)),
    )
