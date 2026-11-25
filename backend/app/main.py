"""Precedent's web server: a health check and the GitHub webhook."""
import hashlib
import hmac
import json
import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from psycopg.types.json import Jsonb

from app import config  # loads backend/.env
from app.api import router as api_router
from app.jobs import admit, forget_owner, forget_repos, run_job
from app.redeliver import start_background_sweeps

WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    print(f"[startup] GitHub App key: {config.describe_github_key()}", flush=True)
    start_background_sweeps()
    yield


app = FastAPI(title="Precedent", lifespan=lifespan)
app.include_router(api_router)


@app.get("/health")
def health():
    with psycopg.connect(config.DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
    return {"status": "ok", "pgvector": row[0] if row else None}


def verify_signature(body: bytes, signature: str | None) -> None:
    """Reject any request that wasn't signed by GitHub with our secret."""
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


def plan_job(event: str, payload: dict) -> tuple[str, int] | None:
    """Decide what to do for a webhook event: ("check" or "extract", PR number), or None."""
    sender = payload.get("sender") or {}
    if sender.get("type") == "Bot":
        return None  # ignore bots, including Precedent itself, so we never react to our own comments

    action = payload.get("action")

    if event == "pull_request":
        pr = payload["pull_request"]
        if action in {"opened", "reopened", "synchronize", "ready_for_review"} and not pr.get("draft"):
            return ("check", pr["number"])
        if action == "closed":
            return ("extract", pr["number"])

    if event == "pull_request_review_comment" and action in {"created", "edited"}:
        return ("extract", payload["pull_request"]["number"])

    if event == "pull_request_review" and action == "submitted":
        # Inline comments already arrive as their own events; only a review's summary text adds anything.
        if (payload.get("review") or {}).get("body"):
            return ("extract", payload["pull_request"]["number"])

    if event == "issue_comment" and action in {"created", "edited"}:
        issue = payload.get("issue") or {}
        if "pull_request" in issue:  # a comment on a PR, not on a plain issue
            return ("extract", issue["number"])

    return None



def repos_removed(event: str, payload: dict) -> list[str]:
    """Repositories Precedent was just removed from (their data should be deleted)."""
    if event == "installation_repositories" and payload.get("action") == "removed":
        return [r["full_name"] for r in payload.get("repositories_removed") or []]
    return []


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(...),
    x_github_delivery: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
):
    body = await request.body()
    verify_signature(body, x_hub_signature_256)
    payload = json.loads(body)

    action = payload.get("action")
    repository = payload.get("repository") or {}
    repo = repository.get("full_name")
    private = bool(repository.get("private"))

    # Precedent removed from some repositories, or uninstalled from an account: forget their data.
    forget_repos(repos_removed(x_github_event, payload))
    if x_github_event == "installation" and action == "deleted":
        forget_owner(((payload.get("installation") or {}).get("account") or {}).get("login"))

    planned = plan_job(x_github_event, payload)
    job = planned[0] if planned else None

    with psycopg.connect(config.DATABASE_URL) as conn:
        status, note = admit(conn, repo, private) if planned else ("ignored", None)
        conn.execute(
            """
            INSERT INTO webhook_events (delivery_id, event, action, repo, payload, job, status, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (delivery_id) DO UPDATE
                SET job = EXCLUDED.job, status = EXCLUDED.status, error = EXCLUDED.error, finished_at = NULL,
                    attempts = 0  -- a resend from GitHub gets a fresh set of retries
            """,
            # Nothing from a private repository's payload is kept.
            (x_github_delivery, x_github_event, action, repo, Jsonb({} if private else payload),
             job, status, note),
        )

    print(f"[webhook] {x_github_event} {action or ''} {repo or ''} -> {job or 'ignored'} ({status})", flush=True)

    if status == "queued":
        background_tasks.add_task(run_job, x_github_delivery, job, repo, planned[1])

    return {"ok": True, "job": job, "status": status}